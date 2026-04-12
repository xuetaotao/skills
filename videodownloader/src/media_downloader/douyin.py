# -*- coding: utf-8 -*-
"""
抖音视频下载器
独立于 yt-dlp 的抖音专用下载模块，支持：
- 单视频无水印下载
- 图集/图片下载
- 音频提取
- 短链接自动解析
"""

import os
import re
import json
import time
import requests
from datetime import datetime
from urllib.parse import urlparse, urljoin


class DouyinDownloader:
    """抖音视频下载器"""

    # 移动端 User-Agent
    MOBILE_UA = (
        'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/116.0.0.0 Mobile Safari/537.36'
    )

    # PC 端 User-Agent
    PC_UA = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )

    def __init__(self, output_dir='./output', proxy=None, cookie=None,
                 timeout=30, progress_callback=None):
        """
        初始化抖音下载器

        Args:
            output_dir: 输出目录
            proxy: 代理地址
            cookie: Cookie 字符串或文件路径
            timeout: 请求超时时间
            progress_callback: 进度回调函数
        """
        self.output_dir = output_dir
        self.proxy = proxy
        self.cookie = cookie
        self.timeout = timeout
        self.progress_callback = progress_callback

        # 请求会话
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.MOBILE_UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://www.douyin.com/',
        })

        if proxy:
            self.session.proxies = {
                'http': proxy,
                'https': proxy,
            }

        if cookie:
            self._setup_cookie(cookie)

        # 下载统计
        self.downloaded_count = 0
        self.failed_count = 0

    def _log(self, msg):
        """输出日志"""
        if self.progress_callback:
            self.progress_callback(msg)
        else:
            print(msg)

    def _setup_cookie(self, cookie):
        """设置 Cookie"""
        if os.path.isfile(cookie):
            try:
                with open(cookie, 'r', encoding='utf-8') as f:
                    cookie_str = f.read().strip()
                self.session.headers['Cookie'] = cookie_str
            except Exception as e:
                self._log(f"[-] 读取 Cookie 文件失败: {e}")
        else:
            self.session.headers['Cookie'] = cookie

    @staticmethod
    def is_douyin_url(url):
        """判断 URL 是否是抖音链接"""
        douyin_domains = [
            'douyin.com', 'www.douyin.com', 'v.douyin.com',
            'iesdouyin.com', 'www.iesdouyin.com',
        ]
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return any(d in domain for d in douyin_domains)

    @staticmethod
    def classify_url(url):
        """
        分类抖音 URL 类型

        Returns:
            str: 'video' - 单视频, 'user' - 用户主页, 'note' - 图文,
                 'short' - 短链接, 'unknown' - 未知
        """
        url_lower = url.lower()

        if '/user/' in url_lower:
            return 'user'

        if 'modal_id=' in url_lower:
            return 'video'

        if '/video/' in url_lower:
            return 'video'

        if '/note/' in url_lower:
            return 'note'

        if 'v.douyin.com' in url_lower:
            return 'short'

        return 'unknown'

    def _resolve_short_url(self, url):
        """
        解析短链接，获取真实 URL

        短链接如 https://v.douyin.com/OKWd6BfV5MA/ 会重定向到
        https://www.douyin.com/video/7620404072419577134 之类

        Returns:
            str: 解析后的真实 URL
        """
        try:
            self._log(f"[*] 解析短链接: {url}")
            # 不自动跟随重定向，手动获取 Location
            resp = self.session.get(url, allow_redirects=False, timeout=self.timeout)

            # 可能有多级重定向
            location = resp.headers.get('Location', '')
            max_redirects = 5
            redirects = 0
            while location and redirects < max_redirects:
                self._log(f"[*] 重定向 -> {location}")
                if 'douyin.com/video/' in location or 'douyin.com/note/' in location:
                    return location
                try:
                    resp = self.session.get(location, allow_redirects=False, timeout=self.timeout)
                    location = resp.headers.get('Location', '')
                except Exception:
                    break
                redirects += 1

            # 如果手动跟踪失败，用自动重定向
            resp = self.session.get(url, allow_redirects=True, timeout=self.timeout)
            real_url = resp.url
            self._log(f"[+] 真实 URL: {real_url}")
            return real_url
        except Exception as e:
            self._log(f"[-] 解析短链接失败: {e}")
            return url

    def _extract_video_id(self, url):
        """
        从 URL 中提取视频 ID

        支持:
        - https://www.douyin.com/video/7620404072419577134
        - https://www.douyin.com/user/self?modal_id=7620404072419577134
        - https://www.iesdouyin.com/share/video/7620404072419577134
        - https://www.douyin.com/discover?modal_id=7620404072419577134
        """
        # modal_id 参数
        match = re.search(r'modal_id=(\d+)', url)
        if match:
            return match.group(1)

        # /video/ 路径
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)

        # /note/ 路径 (图文)
        match = re.search(r'/note/(\d+)', url)
        if match:
            return match.group(1)

        # /share/video/ 路径
        match = re.search(r'/share/video/(\d+)', url)
        if match:
            return match.group(1)

        return None

    def _extract_sec_uid(self, url):
        """从用户主页 URL 中提取 sec_uid"""
        match = re.search(r'/user/([A-Za-z0-9_-]+)', url)
        if match:
            return match.group(1)
        return None

    def fetch_video_info(self, video_id):
        """
        获取单个视频信息

        通过 iesdouyin.com 的分享页面获取视频数据

        Args:
            video_id: 视频 ID

        Returns:
            dict: 视频信息，失败返回 None
        """
        try:
            url = f'https://www.iesdouyin.com/share/video/{video_id}/'
            self._log(f"[*] 获取视频信息: {video_id}")

            # 使用移动端 UA + Referer 请求
            headers = {
                'User-Agent': self.MOBILE_UA,
                'Referer': 'https://www.douyin.com/',
            }
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            resp.raise_for_status()

            # 从 HTML 中提取视频数据 - 方式1: window._ROUTER_DATA
            pattern = re.compile(
                r'window\._ROUTER_DATA\s*=\s*(.*?)</script>',
                re.DOTALL
            )
            match = pattern.search(resp.text)

            if match:
                return self._parse_router_data(match.group(1).strip())

            # 方式2: RENDER_DATA (新版页面)
            pattern2 = re.compile(
                r'<script\s+id="RENDER_DATA"\s+type="application/json">.*?</script>',
                re.DOTALL
            )
            match2 = pattern2.search(resp.text)
            if not match2:
                # 尝试另一种 RENDER_DATA 格式
                pattern3 = re.compile(
                    r'window\.__RENDER_DATA__\s*=\s*(.*?)</script>',
                    re.DOTALL
                )
                match2 = pattern3.search(resp.text)

            if match2:
                self._log("[-] 发现 RENDER_DATA 格式，暂不支持自动解析")
                self._log("[!] 请尝试使用 Cookie 方式访问")

            self._log("[-] 未找到视频数据 (页面结构可能已变更)")
            self._log("[!] 可能需要提供 Cookie 来访问该视频")
            return None

        except json.JSONDecodeError as e:
            self._log(f"[-] 解析视频数据失败: {e}")
            return None
        except requests.exceptions.HTTPError as e:
            self._log(f"[-] HTTP 错误: {e}")
            if e.response.status_code == 404:
                self._log("[-] 视频可能已被删除或设为私密")
            return None
        except Exception as e:
            self._log(f"[-] 获取视频信息失败: {e}")
            return None

    def _parse_router_data(self, json_str):
        """
        解析 window._ROUTER_DATA JSON 数据

        Args:
            json_str: JSON 字符串

        Returns:
            dict: 标准化的视频信息
        """
        try:
            router_data = json.loads(json_str)
        except json.JSONDecodeError:
            self._log("[-] JSON 解析失败")
            return None

        loader_data = router_data.get('loaderData', {})

        # 查找包含 videoInfoRes 的节点
        # 可能的 key: video_(id)/page, video_xxx/page 等
        for key, value in loader_data.items():
            if not isinstance(value, dict):
                continue
            if 'videoInfoRes' in value:
                video_info_res = value['videoInfoRes']
                if not isinstance(video_info_res, dict):
                    continue
                item_list = video_info_res.get('item_list', [])
                if item_list and isinstance(item_list[0], dict):
                    return self._parse_video_item(item_list[0])

        # 兜底: 查找含 video 关键字且非 None 的节点
        for key, value in loader_data.items():
            if not isinstance(value, dict):
                continue
            if 'video' in key.lower() and value.get('videoInfoRes'):
                video_info_res = value['videoInfoRes']
                item_list = video_info_res.get('item_list', [])
                if item_list:
                    return self._parse_video_item(item_list[0])

        self._log(f"[-] 未找到视频数据节点，可用 keys: {list(loader_data.keys())}")
        return None

    def _parse_video_item(self, item):
        """
        解析视频条目数据

        Args:
            item: 抖音 API 返回的视频条目

        Returns:
            dict: 标准化的视频信息
        """
        info = {
            'video_id': item.get('aweme_id', ''),
            'title': item.get('desc', ''),
            'author': item.get('author', {}).get('nickname', ''),
            'author_id': item.get('author', {}).get('unique_id', '') or item.get('author', {}).get('sec_uid', ''),
            'create_time': item.get('create_time', 0),
            'duration': item.get('duration', 0) / 1000 if item.get('duration') else 0,
            'statistics': {
                'digg_count': item.get('statistics', {}).get('digg_count', 0),
                'comment_count': item.get('statistics', {}).get('comment_count', 0),
                'share_count': item.get('statistics', {}).get('share_count', 0),
                'play_count': item.get('statistics', {}).get('play_count', 0),
            },
            'video_url': None,
            'video_urls': [],
            'cover_url': None,
            'music_url': None,
            'images': [],
            'is_image_set': False,
        }

        # 视频地址
        video = item.get('video', {})
        play_addr = video.get('play_addr', {})

        # 方法1: 通过 play_addr.uri 构造无水印 URL (最可靠)
        video_uri = play_addr.get('uri', '')
        if video_uri:
            info['video_url'] = f'https://www.douyin.com/aweme/v1/play/?video_id={video_uri}'
            info['video_urls'] = [info['video_url']]

        # 方法2: 通过 url_list + playwm -> play 替换
        url_list = play_addr.get('url_list', [])
        if url_list and not info['video_url']:
            info['video_url'] = url_list[0].replace('playwm', 'play')
            info['video_urls'] = [u.replace('playwm', 'play') for u in url_list]

        # 方法3: bit_rate 中的高画质
        if not info['video_url']:
            bit_rate = video.get('bit_rate', [])
            if bit_rate:
                # 取最高画质
                best = max(bit_rate, key=lambda x: x.get('bit_rate', 0))
                best_play_addr = best.get('play_addr', {})
                best_uri = best_play_addr.get('uri', '')
                if best_uri:
                    info['video_url'] = f'https://www.douyin.com/aweme/v1/play/?video_id={best_uri}'
                    best_urls = best_play_addr.get('url_list', [])
                    info['video_urls'] = [u.replace('playwm', 'play') for u in best_urls]

        # 封面
        cover = video.get('cover', {})
        cover_urls = cover.get('url_list', [])
        if cover_urls:
            info['cover_url'] = cover_urls[0]

        # 动态封面
        dynamic_cover = video.get('dynamic_cover', {})
        dynamic_cover_urls = dynamic_cover.get('url_list', [])

        # 背景音乐
        music = item.get('music', {})
        music_url = music.get('play_url', {}).get('url', '')
        if music_url:
            info['music_url'] = music_url

        # 图集
        images = item.get('images', [])
        if images:
            info['is_image_set'] = True
            for img in images:
                img_urls = img.get('url_list', [])
                if img_urls:
                    info['images'].append(img_urls[0])

        return info

    def download_video(self, video_info, output_dir=None):
        """
        下载单个视频

        Args:
            video_info: 视频信息字典
            output_dir: 输出目录

        Returns:
            bool: 是否成功
        """
        save_dir = output_dir or self.output_dir
        os.makedirs(save_dir, exist_ok=True)

        video_url = video_info.get('video_url')
        video_urls = video_info.get('video_urls', [])

        if not video_url and not video_urls:
            self._log("[-] 无视频下载地址")
            return False

        # 生成文件名
        title = video_info.get('title', video_info.get('video_id', 'video'))
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = video_info.get('video_id', 'video')
        filename = f"{safe_title}.mp4"
        filepath = os.path.join(save_dir, filename)

        # 避免重复下载
        if os.path.exists(filepath):
            self._log(f"[~] 文件已存在，跳过: {filename}")
            return True

        # 尝试多个 URL
        urls_to_try = [video_url] + [u for u in video_urls if u != video_url]
        download_headers = {
            'User-Agent': self.MOBILE_UA,
            'Referer': 'https://www.douyin.com/',
        }

        for i, try_url in enumerate(urls_to_try):
            if not try_url:
                continue
            try:
                self._log(f"[*] 下载视频: {filename}" + (f" (备选链接 {i})" if i > 0 else ""))
                resp = self.session.get(try_url, headers=download_headers,
                                        timeout=self.timeout, stream=True)
                resp.raise_for_status()

                # 检查是否返回了有效内容
                content_type = resp.headers.get('content-type', '')
                if 'video' not in content_type and 'octet-stream' not in content_type:
                    self._log(f"[-] 返回内容类型异常: {content_type}")
                    continue

                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0

                with open(filepath, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # 简单进度提示
                            if total_size and downloaded % (512 * 1024) < 8192:
                                percent = downloaded / total_size * 100
                                self._log(f"    下载进度: {percent:.0f}%")

                file_size_mb = downloaded / 1024 / 1024
                if file_size_mb < 0.01:
                    # 文件太小，可能下载失败
                    os.remove(filepath)
                    self._log(f"[-] 下载文件过小 ({file_size_mb:.2f}MB)，可能失败")
                    continue

                self._log(f"[+] 下载完成: {filename} ({file_size_mb:.1f}MB)")
                self.downloaded_count += 1
                return True

            except Exception as e:
                self._log(f"[-] 下载失败 (链接 {i}): {e}")
                if os.path.exists(filepath):
                    os.remove(filepath)
                continue

        self._log("[-] 所有下载链接均失败")
        self.failed_count += 1
        return False

    def download_images(self, video_info, output_dir=None):
        """
        下载图集

        Args:
            video_info: 视频信息字典
            output_dir: 输出目录

        Returns:
            bool: 是否成功
        """
        save_dir = output_dir or self.output_dir
        os.makedirs(save_dir, exist_ok=True)

        images = video_info.get('images', [])
        if not images:
            self._log("[-] 无图片可下载")
            return False

        title = video_info.get('title', video_info.get('video_id', 'images'))
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = video_info.get('video_id', 'images')

        success_count = 0
        download_headers = {
            'User-Agent': self.MOBILE_UA,
            'Referer': 'https://www.douyin.com/',
        }

        for i, img_url in enumerate(images):
            filename = f"{safe_title}_{i+1:03d}.jpg"
            filepath = os.path.join(save_dir, filename)

            if os.path.exists(filepath):
                self._log(f"[~] 文件已存在，跳过: {filename}")
                success_count += 1
                continue

            try:
                self._log(f"[*] 下载图片: {filename}")
                resp = self.session.get(img_url, headers=download_headers,
                                        timeout=self.timeout)
                resp.raise_for_status()

                with open(filepath, 'wb') as f:
                    f.write(resp.content)

                self._log(f"[+] 下载完成: {filename}")
                success_count += 1

            except Exception as e:
                self._log(f"[-] 下载失败: {filename} - {e}")
                self.failed_count += 1

        self.downloaded_count += success_count
        return success_count > 0

    def download_audio(self, video_info, output_dir=None):
        """
        下载背景音乐/音频

        Args:
            video_info: 视频信息字典
            output_dir: 输出目录

        Returns:
            bool: 是否成功
        """
        save_dir = output_dir or self.output_dir
        os.makedirs(save_dir, exist_ok=True)

        music_url = video_info.get('music_url')
        if not music_url:
            self._log("[-] 无音频下载地址")
            return False

        title = video_info.get('title', video_info.get('video_id', 'audio'))
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:50].rstrip()
        if not safe_title:
            safe_title = video_info.get('video_id', 'audio')
        filename = f"{safe_title}.mp3"
        filepath = os.path.join(save_dir, filename)

        if os.path.exists(filepath):
            self._log(f"[~] 文件已存在，跳过: {filename}")
            return True

        download_headers = {
            'User-Agent': self.MOBILE_UA,
            'Referer': 'https://www.douyin.com/',
        }

        try:
            self._log(f"[*] 下载音频: {filename}")
            resp = self.session.get(music_url, headers=download_headers,
                                    timeout=self.timeout, stream=True)
            resp.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size_mb = os.path.getsize(filepath) / 1024 / 1024
            self._log(f"[+] 下载完成: {filename} ({file_size_mb:.1f}MB)")
            self.downloaded_count += 1
            return True

        except Exception as e:
            self._log(f"[-] 下载失败: {filename} - {e}")
            self.failed_count += 1
            return False

    def _generate_subdir_name(self, video_info):
        """
        生成子目录名

        格式: douyin-{作者}-{标题前15字}-{时间}
        """
        author = video_info.get('author', '')
        title = video_info.get('title', '')
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title)[:15].rstrip()
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')

        parts = [p for p in ['douyin', author, safe_title, time_str] if p]
        return '-'.join(parts)

    def run(self, url, mode='video'):
        """
        运行下载流程

        Args:
            url: 抖音 URL
            mode: 下载模式 - 'video'/'audio'/'info'

        Returns:
            bool: 是否成功
        """
        self._log("=" * 60)
        self._log(f"抖音下载器 - {mode} 模式")
        self._log("=" * 60)
        self._log(f"地址: {url}")
        self._log(f"输出目录: {os.path.abspath(self.output_dir)}")
        self._log("=" * 60)

        # 解析短链接
        url_type = self.classify_url(url)
        if url_type == 'short':
            url = self._resolve_short_url(url)
            url_type = self.classify_url(url)

        # 提取视频 ID
        video_id = self._extract_video_id(url)

        if url_type == 'user' and not video_id:
            self._log("[-] 用户主页链接需要指定具体视频 (modal_id 参数)")
            self._log("[!] 请复制单个视频的分享链接，而非用户主页链接")
            self._log("[!] 提示: 在抖音 App 中打开视频 -> 分享 -> 复制链接")
            return False

        if not video_id:
            self._log("[-] 无法从 URL 中提取视频 ID")
            self._log("[!] 请使用视频分享链接，例如:")
            self._log("    https://v.douyin.com/xxxxxx/")
            self._log("    https://www.douyin.com/video/7620404072419577134")
            return False

        # 获取视频信息
        video_info = self.fetch_video_info(video_id)
        if not video_info:
            self._log("[-] 无法获取视频信息")
            self._log("[!] 可能原因:")
            self._log("    1) 视频已被删除或设为私密")
            self._log("    2) 需要登录 Cookie (--cookie-file)")
            self._log("    3) 网络问题或地区限制")
            return False

        # 信息查看模式
        if mode == 'info':
            self._print_video_info(video_info)
            return True

        # 生成子目录
        subdir_name = self._generate_subdir_name(video_info)
        save_dir = os.path.join(self.output_dir, subdir_name)

        # 显示信息摘要
        self._log(f"[+] 标题: {video_info.get('title', 'N/A')}")
        self._log(f"[+] 作者: {video_info.get('author', 'N/A')}")
        self._log(f"[+] 类型: {'图集' if video_info.get('is_image_set') else '视频'}")

        # 下载
        start_time = time.time()

        if video_info.get('is_image_set'):
            success = self.download_images(video_info, save_dir)
        elif mode == 'audio':
            success = self.download_audio(video_info, save_dir)
        else:
            success = self.download_video(video_info, save_dir)

        elapsed_time = time.time() - start_time

        # 统计
        self._log("\n" + "=" * 60)
        self._log("下载完成!")
        self._log(f"成功: {self.downloaded_count}")
        self._log(f"失败: {self.failed_count}")
        self._log(f"总耗时: {elapsed_time:.2f} 秒")
        if save_dir:
            self._log(f"保存位置: {os.path.abspath(save_dir)}")
        self._log("=" * 60)

        return success

    def _print_video_info(self, info):
        """打印视频信息"""
        self._log("=" * 60)
        self._log(f"视频 ID: {info.get('video_id', 'N/A')}")
        self._log(f"标题: {info.get('title', 'N/A')}")
        self._log(f"作者: {info.get('author', 'N/A')} (ID: {info.get('author_id', 'N/A')})")
        self._log(f"时长: {self._format_duration(info.get('duration', 0))}")
        self._log(f"类型: {'图集' if info.get('is_image_set') else '视频'}")

        stats = info.get('statistics', {})
        self._log(f"播放量: {stats.get('play_count', 'N/A')}")
        self._log(f"点赞数: {stats.get('digg_count', 'N/A')}")
        self._log(f"评论数: {stats.get('comment_count', 'N/A')}")
        self._log(f"分享数: {stats.get('share_count', 'N/A')}")

        if info.get('is_image_set'):
            self._log(f"图片数: {len(info.get('images', []))}")
        else:
            video_url = info.get('video_url', 'N/A')
            self._log(f"视频链接: {video_url[:100]}..." if len(str(video_url)) > 100 else f"视频链接: {video_url}")

        music_url = info.get('music_url')
        self._log(f"音乐链接: {music_url[:80] if music_url else 'N/A'}")
        self._log("=" * 60)

    @staticmethod
    def _format_duration(seconds):
        """格式化时长"""
        if not seconds:
            return "N/A"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}:{secs:02d}"

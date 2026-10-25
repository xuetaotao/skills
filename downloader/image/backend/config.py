# -*- coding: utf-8 -*-
"""默认参数与图片识别规则（命令行和图形界面共用）"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'outputs')   # 每次下载在这里新建 {域名}-{标题}-{时间}/

NUM_THREADS = 8           # 并发下载数
TIMEOUT = 15              # 单个请求超时（秒）
RETRIES = 3               # 网页和图片请求失败后的重试次数

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')

IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'avif', 'tif', 'tiff', 'heic'}

# 懒加载属性优先于 src：src 往往是占位图
LAZY_ATTRS = ('data-original', 'data-src', 'data-lazy-src', 'data-actualsrc', 'data-url')

# 以下关键词只在 class/id 的词首或 -/_ 之后匹配
# 图片自身的 class/id 命中则视为图标类小图
ICON_KEYWORDS = [
    'icon', 'logo', 'avatar', 'btn', 'button', 'arrow', 'nav', 'emoji', 'smiley',
    'badge', 'favicon', 'gravatar', 'thumbnail',
]
# 祖先元素命中则视为正文以外的区域（推荐、评论、页眉页脚、广告）
EXCLUDED_AREA_KEYWORDS = [
    'sidebar', 'widget', 'recommend', 'related', 'similar', 'suggest', 'popular',
    'trending', 'recent', 'latest', 'comment', 'footer', 'header', 'aside', 'extra',
    'bottom-article', 'more-article', 'other-article', 'item-thumb', 'thumb-list',
    'card-list', 'advertisement', 'ad-', 'sponsor',
]
# 先遇到这些正文容器就不再往上检查排除区域
CONTENT_AREA_KEYWORDS = [
    'article-fulltext', 'article-content', 'article-body', 'entry-content', 'entry-body',
    'post-content', 'post-body', 'content-body', 'main-content', 'main-body',
]

# -*- coding: utf-8 -*-
"""默认参数、画质与格式映射（命令行和图形界面共用）"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'outputs')   # 每次下载在这里新建 {来源}-{标题}-{时间}/

TIMEOUT = 30              # 网络超时（秒）
THREADS = 8               # m3u8 分片并发数
HLS_RETRIES = 4           # 单个分片失败后的重试次数

PC_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
MOBILE_UA = ('Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 '
             '(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36')

# 画质选项 → yt-dlp 格式字符串；没有 ffmpeg 时会去掉需要合并的 “+” 部分
QUALITY_FORMATS = {
    'best': 'bestvideo+bestaudio/best',
    '2160': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
    '1080': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    '720': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
    '480': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
    '360': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
    'single': 'best',
}
AUDIO_FORMATS = ('best', 'mp3', 'm4a', 'flac', 'wav', 'aac', 'opus')
SUB_LANGS = 'zh.*,en.*'   # 字幕语言，逗号分隔，支持正则

# YouTube 解算播放地址需要 JavaScript 运行时，装了哪个用哪个
JS_RUNTIMES = {'deno': {}, 'node': {}, 'bun': {}}

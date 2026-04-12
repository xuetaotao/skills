# -*- coding: utf-8 -*-
"""
音视频下载工具包
基于 yt-dlp，支持视频和音频下载
内置抖音专用下载器、MacCMS 解析器、RouVideo 解析器
"""

__version__ = "1.0.0"

from .core import MediaDownloader
from .douyin import DouyinDownloader
from .maccms import MacCMSDownloader
from .rouvideo import RouVideoDownloader

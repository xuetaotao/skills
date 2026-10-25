# -*- coding: utf-8 -*-
"""逐个探测站点（只解析、不下载）：python scripts/probes/probe_sites.py [网址 ...]

不带参数时读取项目根目录 test_sites.md 里的网址。每个网址走一遍 info 模式，输出用的哪个解析器、
标题、时长，以及 yt-dlp 的可用格式数或专用解析器是否拿到了视频地址，用来排查某个站点改版或失效。
"""
import os
import re
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)
from backend.common import format_duration  # noqa: E402
from backend.core import MediaDownloader  # noqa: E402

VIDEO_URL_KEYS = ('videoUrl', 'video_url', 'url', 'play_url')


def site_urls():
    path = os.path.join(PROJECT_DIR, 'test_sites.md')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return re.findall(r'^\s*-\s*(https?://[^\s（(]+)', f.read(), re.M)


def probe(url):
    t = time.time()
    logs, infos = [], []
    md = MediaDownloader(url, mode='info', progress_callback=logs.append, info_callback=infos.append)
    ok = md.run()
    route = next((l.split('检测到', 1)[1].split('，')[0] for l in logs if '检测到' in l), 'yt-dlp')
    info = infos[0] if infos else {}
    if not ok or not info:
        err = next((l for l in reversed(logs) if l.startswith('[-]')), '没有拿到信息')
        return f"[{route}] 失败：{err[4:120]}  {time.time() - t:.1f}s"
    detail = ''
    if info.get('formats'):
        detail = f"格式 {len(info['formats'])} 个"
    elif md.info:
        has_url = any(isinstance(md.info.get(k), str) and md.info[k].startswith('http') for k in VIDEO_URL_KEYS)
        detail = '视频地址 有' if has_url else '视频地址 无（可能需要登录或页面改版）'
    elif info.get('_type') == 'playlist':
        detail = f"播放列表 {len(info.get('entries') or [])} 个"
    return (f"[{route}] {(info.get('title') or '')[:30]}  时长 {format_duration(info.get('duration'))}  "
            f"{detail}  {time.time() - t:.1f}s")


def main():
    urls = sys.argv[1:] or site_urls()
    if not urls:
        print("用法：python scripts/probes/probe_sites.py <网址> ...（或在 test_sites.md 里列出网址）")
        return
    for url in urls:
        try:
            result = probe(url)
        except Exception as e:  # noqa: BLE001
            result = f"失败：{type(e).__name__}: {e}"
        print(f"{url}\n    {result}")


if __name__ == "__main__":
    main()

"""路径、账号定位、关键词表、抓取参数。

数据目录默认就是本项目目录；设置环境变量 WXPUB_DIR 可以指到别处（沿用旧脚本的约定）。
"""

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("WXPUB_DIR") or PROJECT_DIR).resolve()

DATA_DIR = WORKSPACE / "data"
RAW_DIR = DATA_DIR / "raw"               # 后台页面原始快照（历史证据，不随意删除）
RAW_HISTORY_DIR = RAW_DIR / "history"    # 重新抓取前，被覆盖的旧快照移到这里
QR_PATH = RAW_DIR / "qr" / "qr.png"
PROCESSED_DIR = DATA_DIR / "processed"   # 由 raw 派生，可随时重建
RECOMMEND_DIR = DATA_DIR / "topic_recommendations"
BROWSER_PROFILE = DATA_DIR / "browser_profile"  # Playwright 登录态，会话有效期内免扫码
REPORTS_DIR = WORKSPACE / "reports"
FRONTEND_DIR = PROJECT_DIR / "frontend"

PORT = 8332
ACCOUNT_NAME = "一点财知"
REPORT_PREFIX = "公众号数据分析与创作指引_"

# ---- 账号定位与标题规律（报告、基准、预测共用）----
POSITIONING = ["科技", "商业", "金融"]
BRANDS = ["苹果", "微信", "百度", "抖音", "Claude", "中国银行", "腾讯", "阿里", "微软", "谷歌", "OpenAI", "Meta", "字节"]
CONFLICT = ["也", "越来越", "不再", "扛不住", "归零", "彻底", "第一次", "终于", "崩", "逆袭", "爆发", "凉了", "慌了", "醒悟",
            "治好", "寄给"]
HIGH_FOLLOW_TOPICS = ["科技", "商业", "金融", "理财", "投资", "基金", "股票", "财经",
                      "AI", "人工智能", "微信", "工具", "互联网", "技术", "经济",
                      "省钱", "技巧", "方法", "搜一搜", "App", "银行"]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
TRAFFIC_SOURCES = ["推荐", "搜一搜", "公众号主页", "公众号消息", "其它", "聊天会话", "朋友圈"]
AGE_ORDER = ["18岁以下", "18-25岁", "26-35岁", "36-45岁", "46-60岁", "60岁以上", "未知"]

# 读者画像只聚合「推荐占比 ≥ 50% 且阅读 ≥ 50」的单篇，低样本文章噪声太大
PROFILE_MIN_READS = 50
PROFILE_MIN_RECOMMEND = 50
HIGH_ENGAGEMENT = 5.0  # 互动率（%）达到这个值算高互动

# ---- 公众号后台抓取 ----
MP_HOME = "https://mp.weixin.qq.com/"
PUBLISH_URL = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin={begin}&count=20&token={token}&lang=zh_CN"
DETAIL_URL = ("https://mp.weixin.qq.com/misc/appmsganalysis?action=detailpage&msgid={msgid}_1&publish_date={date}"
              "&type=int&pageVersion=1&token={token}&lang=zh_CN")
# 菜单里找不到链接时的兜底地址
CONTENT_ANALYSIS_URL = "https://mp.weixin.qq.com/misc/appmsganalysis?action=report&token={token}&lang=zh_CN"
USER_ANALYSIS_URL = "https://mp.weixin.qq.com/misc/useranalysis?&token={token}&lang=zh_CN"

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
VIEWPORT = {"width": 1280, "height": 900}
LOGIN_TIMEOUT = 180          # 秒：等扫码
QR_REFRESH = 100             # 秒：二维码约 2 分钟过期，到点刷新登录页
NAV_TIMEOUT = 45_000         # 毫秒
PAGE_SETTLE = 3_500          # 毫秒：SPA 渲染图表的时间
MAX_PUBLISH_PAGES = 200      # 发表记录每页 20 条，到空页即停；命中上限说明可能漏抓
DETAIL_RECENT_DAYS = 30      # 详情页只统计发表后 30 天，这段时间内的文章每次都重抓

DETAIL_MODES = {
    "missing_recent": "缺详情的文章 + 近 30 天发表的文章（推荐）",
    "recent": "只抓近 30 天发表的文章",
    "missing": "只补抓缺详情的文章",
    "all": "全部文章重抓（较慢）",
    "none": "不抓详情页",
}

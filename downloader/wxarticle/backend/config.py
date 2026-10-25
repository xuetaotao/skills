"""全局常量：路径、浏览器参数、各种等待时间。"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / 'outputs'

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
VIEWPORT = {'width': 1280, 'height': 900}

# 截图像素倍率：2 倍字迹清晰，文件约为 1 倍的 2~3 倍
SCALE = 2
# 截图高度（物理像素）超过这个值就退回 1 倍，太高的图很多看图软件打不开
MAX_SCREENSHOT_HEIGHT = 32000

# 毫秒
NAV_TIMEOUT = 60_000      # 打开页面
CONTENT_TIMEOUT = 20_000  # 等正文 #js_content 出现
IMAGE_TIMEOUT = 30_000    # 等正文图片全部加载完
SCROLL_PAUSE = 120        # 滚动触发懒加载时每屏停留

PDF_MARGIN = '20px'

# 微信提示页上的文字：出现任意一个就说明文章打不开，不用再干等
BLOCKED_HINTS = (
    '根据作者隐私设置',
    '该内容已被发布者删除',
    '此内容因违规无法查看',
    '此内容被投诉且经审核涉嫌侵权',
    '该公众号已迁移',
    '该账号已被封禁',
    '环境异常',
    '参数错误',
    '链接已过期',
)

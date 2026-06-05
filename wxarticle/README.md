# 微信公众号文章下载器

将微信公众号文章保存为 PDF 和截图的命令行工具。

## 功能特性

- 给定微信公众号文章链接，生成 PDF 和截图
- 自动处理页面滚动，加载懒加载图片
- 支持自定义输出目录

## 安装

```bash
cd wxarticle

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

## 使用方法

### 一键运行（推荐）

```bash
./run.sh "https://mp.weixin.qq.com/s/xxxxx"
```

首次运行会自动创建虚拟环境并安装依赖。

### 手动运行

```bash
cd wxarticle

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium

# 运行
python -m src "https://mp.weixin.qq.com/s/xxxxx"

# 其他选项
python -m src "https://mp.weixin.qq.com/s/xxxxx" -o ./my_output  # 指定输出目录
python -m src "https://mp.weixin.qq.com/s/xxxxx" --pdf-only      # 只生成 PDF
python -m src "https://mp.weixin.qq.com/s/xxxxx" --screenshot-only  # 只生成截图
```

## 目录结构

```
wxarticle/
├── README.md           # 说明文档
├── requirements.txt    # 依赖
├── run.sh              # 一键运行脚本
├── output/             # 输出目录
└── src/
    ├── __init__.py
    ├── __main__.py     # 模块入口
    ├── main.py         # 命令行入口
    ├── fetcher.py      # 文章抓取
    └── generator.py    # PDF/截图生成
```

## 待实现功能

- [ ] 通过公众号名称自动获取最新文章并下载

## 调研备忘（2026-06-05）

调研了 mptext.top / wechat-article 这套方案，评估能否扩展成"输入链接 → 公众号登录 → 下载整篇文章含留言"的应用。结论记录如下，方便后续决策。

### 三类能力的实现路径

1. **正文下载（本项目现状）**：Playwright 渲染文章页 → PDF/截图，纯本地、无需登录、无需抓包。已够用。
   - HTML+本地图导出：存储占用和 PDF 一个量级（都被图片主导，省不了空间），价值在"可编辑/可转格式/可二次加工"而非体积。仅"看/打印"则没必要加。

2. **整号批量枚举**：需扫码登录 `mp.weixin.qq.com` 后台（`getqrcode`→`scan`→`bizlogin`），再用 `searchbiz`/`appmsgpublish` 接口翻页枚举文章。原理是借公众号后台"写文章时可搜索其他公众号文章"的功能。**单独一摊活，且后台有严格频控/风控风险**，需做缓存与限速。

3. **留言 / 阅读量下载（硬门槛）**：留言走 `mp.weixin.qq.com/mp/appmsg_comment?action=getcomment`，强制要求 `key`/`uin`/`pass_ticket`/`__biz` 这组**手机 App 会话凭证**。
   - 公众号后台登录拿不到，链接里也没有，**只能用 mitmproxy 抓包**（手机 WiFi 代理指向电脑 → App 打开文章 → 拦截响应里的 Set-Cookie/凭证）。
   - 凭证 **~30 分钟失效**，且**只对当时打开的那个公众号 `__biz` 有效**，换公众号要重抓。绕不开"手机+代理"，除非用商业版高速通道。
   - 这也是本项目及同类工具下不了留言的根本原因。

### 参考链接

- 下载站（在线工具）：https://down.mptext.top
- 文档站 / 留言抓包教程：https://docs.mptext.top/advanced/wxdown-service.html
- wechat-article-exporter（前端主站，Nuxt/Vue，MIT，11k★）：https://github.com/wechat-article/wechat-article-exporter
- wxdown-service（本地抓包增强服务，Python，mitmproxy）：https://github.com/wechat-article/wxdown-service
- WeChat_Article（exporter 的原理来源）：https://github.com/1061700625/WeChat_Article
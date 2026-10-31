# Skills

AI驱动的个人工具集，基于大语言模型开发各种自动化工具和想法实验。

## 项目列表

### stock/yupen_review

**鱼盆模型复盘** - 本地网站跟踪全球股指、大宗商品、A 股行业指数和个股的鱼盆状态（20 日均线 YES / NO、偏离度、5 档信号），以及美元、中美国债和 PE 百分位，为 AI 生成周度复盘正文提供素材（端口 8325）。原 yupen 日报已合并进来，GitHub Actions 每个交易日晚上把完整版汇总发布到 GitHub Pages。

如果在仓库根目录直接对 AI 说：

- `帮我生成一下鱼盆模型周度复盘`
- `基于最新 review 输出，生成本周鱼盆模型周度复盘`

AI 应按 [stock/yupen_review/prompts/鱼盆模型周度复盘模版.md](stock/yupen_review/prompts/鱼盆模型周度复盘模版.md) 开头注释里的步骤执行，写作和新闻规则以 `stock/yupen_review/prompts/review_preferences.md` 为准。

详情见 [stock/yupen_review/README.md](stock/yupen_review/README.md)

### downloader

**下载工具**，三个独立的 PyQt5 小程序，目录结构和 stock 下的项目一致（`backend/` 逻辑、`frontend/` 界面、`scripts/` 启动与探测脚本），各自带 `.venv`。双击 `scripts\start_gui.bat` 打开图形界面，也可以用 `python -m backend ...` 走命令行。

- [downloader/image](downloader/image/README.md)：批量下载网页里的图片，支持懒加载、原图链接、自动翻页和内容去重
- [downloader/video](downloader/video/README.md)：基于 yt-dlp 下载视频或音频，内置抖音（无水印）、MacCMS 影视站、RouVideo 专用下载器和支持加密与续传的 m3u8 下载器
- [downloader/wxarticle](downloader/wxarticle/README.md)：用 Playwright 把微信公众号文章保存成 PDF 和正文长截图，可一次粘贴多篇，打不开的文章（隐私设置、已删除、环境异常）直接报出原因

### content

**内容创作与公众号运营**，两个本地小网站，目录结构和 stock、downloader 下的项目一致（`backend/` 逻辑、`frontend/` 界面、`scripts/` 启动脚本），各自带 `.venv`。按「复盘与选题 → 观点成稿 → 人工发表 → 数据反馈」串联，两个工作空间保持独立。

- [content/writing](content/writing/README.md)：写作工作台（端口 8331）。按阶段（观点拓展 / 初稿 / 修改反馈 / 质量检查）拼好完整 Prompt 一键复制，文章库保存每一版并逐段对比，本地自检 AI 腔、绝对化表述和需要查证的句子，借公众号的爆款预测器给标题打分
- [content/wxpubaccount](content/wxpubaccount/README.md)：「一点财知」公众号数据分析（端口 8332）。Playwright 扫码登录后台（登录态保存，免重复扫码）抓发表记录、总览和详情页，看阅读、涨粉、互动和读者画像，标题评分、选题推荐，生成 HTML 创作指引报告

统一入口见 [content/README.md](content/README.md)。从仓库根目录发起写作或公众号运营任务时，AI 应先阅读该入口，再按对应子项目的工作流或技能执行。

## 开发说明

所有项目均为 AI Coding 实验，探索如何利用大语言模型自动完成从想法到实现的完整流程。

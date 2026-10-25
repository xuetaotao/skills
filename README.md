# Skills

AI驱动的个人工具集，基于大语言模型开发各种自动化工具和想法实验。

## 项目列表

### yupen

**鱼盆模型量化分析系统** - 基于鱼盆模型的多Agent量化交易分析系统

- 多数据源采集（新浪财经、中证CSIndex、东方财富、腾讯财经、Baostock）
- 多Agent架构协同工作
- 基于20日均线的指数趋势分析
- 自动生成JSON、Markdown、HTML报告
- 每日15:30定时执行

详情见 [yupen/README.md](yupen/README.md)

### stock/yupen_review

**鱼盆模型周度复盘** - 本地网站跟踪全球股指、大宗商品的鱼盆状态和美元、中美国债，为 AI 生成周度复盘正文提供素材（端口 8325）。

如果在仓库根目录直接对 AI 说：

- `帮我生成一下鱼盆模型周度复盘`
- `基于最新 review 输出，生成本周鱼盆模型周度复盘`

AI 应按 [stock/yupen_review/prompts/鱼盆模型周度复盘模版.md](stock/yupen_review/prompts/鱼盆模型周度复盘模版.md) 开头注释里的步骤执行，写作和新闻规则以 `stock/yupen_review/prompts/review_preferences.md` 为准。

详情见 [stock/yupen_review/README.md](stock/yupen_review/README.md)

## 开发说明

所有项目均为 AI Coding 实验，探索如何利用大语言模型自动完成从想法到实现的完整流程。

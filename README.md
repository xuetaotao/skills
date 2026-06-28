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

### stock/review

**鱼盆模型周度复盘** - 基于 yupen 最新行情汇总和财经新闻，生成周度复盘正文。

如果在仓库根目录直接对 AI 说：

- `帮我生成一下鱼盆模型周度复盘`
- `基于最新 review 输出，生成本周鱼盆模型周度复盘`

AI 应先阅读 [stock/review/README.md](stock/review/README.md)，再按其中的“交给 AI 生成周度复盘正文”流程执行：先按当前操作系统刷新行情汇总，读取 `stock/review/review_preferences.md`，再使用 `stock/review/outputs/latest_review_simple.md` 生成正文。

详情见 [stock/review/README.md](stock/review/README.md)

## 开发说明

所有项目均为 AI Coding 实验，探索如何利用大语言模型自动完成从想法到实现的完整流程。

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

## 开发说明

所有项目均为 AI Coding 实验，探索如何利用大语言模型自动完成从想法到实现的完整流程。

# 内容创作与公众号运营

将通用写作流程与公众号运营放在同一分类下，保留两个独立工作空间：写作负责观点与表达，公众号运营负责选题参考和发布后的数据反馈。两个都是本地小网站，目录结构和 stock、downloader 下的项目一致（`backend/` 逻辑、`frontend/` 界面、`scripts/` 启动脚本），各自带 `.venv`。

## 入口

| 工作空间 | 用途 | 启动 | 说明 |
|---|---|---|---|
| writing | 写作台（按阶段拼 Prompt）、文章库与版本对比、本地自检、标题评分 | `writing\scripts\start_server.bat` → <http://127.0.0.1:8331> | [写作工作台](./writing/README.md)、[写作工作流](./writing/WorkFlow.md) |
| wxpubaccount | 「一点财知」扫码抓取后台数据、阅读与涨粉分析、标题评分、选题推荐、HTML 报告 | `wxpubaccount\scripts\start_server.bat` → <http://127.0.0.1:8332> | [公众号数据分析](./wxpubaccount/README.md)、[分析技能](./wxpubaccount/.workbuddy/skills/wxpub-analysis/SKILL.md) |

## 串联流程

1. **复盘与选题**：在公众号分析里「抓取最新数据」，看总览和报告；需要选题时用「选题推荐」。先检查数据日期和分析范围，历史规律只作为参考。
2. **确定主题与想法**：由我选择方向、提供原始观点。已有主题时可直接跳过选题推荐，不必先通过评分。
3. **展开与成稿**：在写作台选「观点拓展」或「初稿」阶段，复制 Prompt 给 AI；想认真写的稿子存成文章，每一版贴回去存为新版本。
4. **修改与质检**：用「修改反馈」提意见；基本满意后先跑一遍「自检」，再用「质量检查」Prompt 做反方审稿、事实风险扫描和去 AI 腔。标题在文章的「标题评分」里比较几个写法。
5. **审核与发表**：由我最终定稿并手动发表，本工作空间不自动发布文章。状态改成「定稿 / 已发表」时会另存 final.md，记下发表日期和链接。
6. **发布后复盘**：数据积累后回到公众号分析抓取、复盘阅读、分享和涨粉；关注有滞后，不把刚发布文章的数据当作最终表现。

核心路径：**数据反馈 → 选题 → 我的主题与想法 → 共创成稿 → 人工发表 → 数据复盘**。

## 对助手的使用入口

- 写文章、拓展观点或修改初稿：先阅读 [写作工作流](./writing/WorkFlow.md)，保持我的立场和最终取舍。需要拼 Prompt 或自检时可用 `python -m backend prompt ...` / `python -m backend check ...`（在 `content/writing/` 下执行，见 [写作工作台](./writing/README.md)）。
- 分析公众号、推荐选题或评估标题：先阅读 [公众号分析技能](./wxpubaccount/.workbuddy/skills/wxpub-analysis/SKILL.md)，按其中的命令执行（在 `content/wxpubaccount/` 下执行 `python -m backend scrape / analyze / predict / recommend`）。
- 分析技能保留在 WorkBuddy 的原有目录中；其他助手按需显式阅读，不依赖新增的自动发现配置。

## 项目边界

- **通用写作原则**归 writing：作者立场、自然表达、事实边界和审核方式，也适用于非公众号文章。
- **账号规则与数据**归 wxpubaccount：科技 / 商业 / 金融定位、历史指标、标题评分和选题反馈，不自动改写通用 Prompt。
- **只有一处只读联系**：写作工作台的标题评分按文件路径加载 `wxpubaccount/backend/prediction.py` 并读它的爆款预测基准，不写公众号那边的任何文件；公众号工作空间不存在时这个功能自动隐藏。
- **评分是参考，不是门槛**：有价值但未通过评分的选题仍可保留，最终由我判断。
- **文章正文不属于可再生产物**：保存在 `writing/articles/`（已 gitignore，按日期与主题分目录，版本只增不改），另行备份或单独版本管理，不放入公众号的 data 或 reports 中。

## 本地数据与迁移

- 公众号的 data（原始快照、清洗数据、选题推荐、浏览器登录态）、reports 和 WorkBuddy 工作日志保持本地存储，继续沿用其 [Git 忽略规则](./wxpubaccount/.gitignore)。
- `data/raw/` 是历史时点的原始证据，重新抓取不保证复现旧值；重新抓取时被覆盖的旧快照会移到 `data/raw/history/`。忽略提交不等于可以随意删除。
- `data/processed/` 和分析报告可在原始快照完整时重新生成（公众号网页「报告」页或 `python -m backend analyze`）；选题推荐记录需要保留时也应一并备份。
- 换电脑时，Git 可还原已提交的代码、文档和技能；历史数据、报告和 `writing/articles/` 需要另外同步。登录态不拷贝，在新电脑上重新扫码即可。
- 各子项目保持独立，不把公众号数据复制进 writing，也不把通用写作 Prompt 复制进分析技能。

## 目录结构

```text
content/
  README.md
  writing/
    README.md  WorkFlow.md  prompts/
    backend/  frontend/  scripts/  requirements.txt
    articles/            # 本地文章库（gitignore）
  wxpubaccount/
    README.md  .gitignore
    backend/  frontend/  scripts/  requirements.txt
    .workbuddy/skills/wxpub-analysis/SKILL.md
    data/  reports/      # 本地数据与报告（gitignore）
```

返回 [仓库首页](../README.md)。

# 公众号「一点财知」数据分析

本地运行的小网站：扫码登录公众号后台抓数据，分析阅读、涨粉和互动，给标题打分、推荐选题，并生成一份可以直接双击打开的 HTML 创作指引报告。目标是围绕账号定位（**科技 / 商业 / 金融**）提高**阅读量 + 粉丝数**。

统一入口见 [内容创作与公众号运营](../README.md)。本目录负责数据和选题参考；观点展开、初稿与定稿在 [写作工作台](../writing/README.md)，文章由我审核后手动发表。

## 快速开始

```bat
scripts\start_server.bat
```

脚本会启动服务并自动打开 <http://127.0.0.1:8332>。第一次用：

1. 点右上角「抓取最新数据」→「开始抓取」，用微信扫页面上的二维码（也可以勾「显示浏览器窗口」在窗口里扫）。
2. 抓取会自动翻完全部发表记录，抓用户分析、内容分析和单篇详情页，然后重新分析、生成报告。首次要把每篇文章的详情页都抓一遍，大约每篇 5 秒。
3. 登录状态保存在 `data/browser_profile/`，会话没过期时下次不用再扫码。

已经有 `data/raw/` 原始快照（例如从旧电脑同步过来）时，不抓也能直接点「用已有快照分析」。

Python 解释器按以下顺序查找：项目下的 `.venv` → WorkBuddy 自带环境 → 系统 PATH 中的 `python`。缺少依赖时脚本会提示安装命令：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
```

Linux / macOS 用 `bash scripts/start_server.sh`。

## 页面

| 页面 | 用途 |
|------|------|
| 总览 | 发文篇数、累计阅读、周均发文、累计关注和月增速、距 100 粉的月数、具名标题杠杆、周二阅读占比、平均互动率；自动生成的要点；每篇阅读柱状图（周二橙色，点柱子进文章）；发布星期、标题类型、流量来源、互动率排行、读者画像（年龄 / 性别 / 地域） |
| 文章 | 分析范围内的全部文章，按任一列排序、搜标题、只看有详情的；点一行看单篇：阅读、完读率、新增关注、分享 / 朋友圈 / 转发、留言收藏、互动率、粉丝活跃度、分享传播力、听全文、阅读渠道和读者画像，可一键「给这个标题打分」 |
| 标题评分 | 一次输入几个标题写法对比打分：阅读潜力、涨粉潜力、互动潜力、定位匹配、饱和度提醒、优化建议和相似的历史文章；右侧是评分依据（当前基准里的杠杆、周二占比、相关系数、有效角度） |
| 选题推荐 | 一句话说需求（“给我推荐3个偏实用的选题，下周二发”），可指定检索词、数量、发文日或只要价值型选题；结果分「通过爆款预测」和「未通过但值得保留」，每个题带理由、热点来源、备选标题、写作要点；可回看历次推荐 |
| 报告 | 切换分析范围（全部 / 口语描述如“近一个月”“2026年至今” / 指定日期 / 最近 N 天）后重新分析；查看、删除 `reports/` 下的 HTML 报告 |
| 数据抓取 | 选详情页范围、是否显示浏览器窗口，开始 / 取消抓取；实时进度、扫码二维码和日志 |
| 术语 | 完读率、互动率、关注/千读、粉丝活跃度、分享传播力、具名主体、冲突词等的白话解释（正文虚线词悬停也可看） |

## 命令行

```bash
python -m backend scrape                       # 扫码抓取（默认弹出浏览器窗口），抓完按上次的范围重新分析
python -m backend scrape --details missing     # 只补抓缺详情的文章；可选 missing_recent(默认) / recent / missing / all / none
python -m backend scrape --headless            # 不弹窗口，需要扫码时打开二维码图片
python -m backend analyze                      # 已抓取的全部文章
python -m backend analyze --nl "近一个月"       # 口语时段；也可 --since 2026-05-27 --until 2026-07-01 / --window 90
python -m backend diagnose                     # 打印星期规律、标题分级、漏斗、相关性
python -m backend predict --title "微信这个更新，AI终于扛不住了" --topics "微信,AI,工具" --day 周二
python -m backend recommend --ask "给我推荐3个偏实用的选题，下周二发"   # 加 --offline 不抓热点
python -m backend range "近两周" "2026年5月"    # 试一下口语时段会被解析成什么
python scripts/probes/probe_snapshots.py       # 打印现有原始快照的解析结果（不联网、不写文件）
```

旧的环境变量 `WXPUB_DIR`（换数据目录）、`WXPUB_RANGE=all` / `WXPUB_SINCE` / `WXPUB_UNTIL` / `WXPUB_WINDOW`（命令行没给范围时生效）仍然支持。

## 数据流

```
扫码登录（data/browser_profile 保存登录态）
  ├─ 发表记录（自动翻页到空页，200 页封顶并告警）→ data/raw/publish_pN.txt
  ├─ 用户分析（累计关注、月增速、新增关注渠道）   → data/raw/user_analysis.txt
  ├─ 内容分析（流量来源、阅读总人数）             → data/raw/content_analysis.txt
  └─ 单篇详情页（完读、分享、关注、渠道、画像）   → data/raw/d2_<appmsg_id>.txt
        被覆盖的旧快照 → data/raw/history/<时间>/
分析（按分析范围）
  → data/processed/recent_articles.json / article_details.json / _window.json
  → data/processed/article_details2.json（reads = 列表页，reads_d2 = 详情页快照）
  → reports/公众号数据分析与创作指引_YYYY-MM-DD.html（11 节）
  → data/processed/hit_baseline.json（爆款预测基准，标题评分和选题推荐都用它）
选题推荐 → data/topic_recommendations/latest.* 和带时间戳的历史
```

页面快照是 Chrome 无障碍树的文本（和以前 agent-browser 的快照同一格式），解析时只认「标签 → 后面第一个符合格式的值」，不依赖页面层级，旧快照和新快照都能解析。

## 口径与边界

- **阅读量以发表记录列表页为准**（= 后台实时看到的值）。详情页快照里的阅读数是抓取那一刻的值，会因去刷量略有出入，只放在 `reads_d2` 供回溯。完读、分享、关注、画像只有详情页有。
- **详情页只统计发表后 30 天**：这段时间内的文章数字还在变，默认每次重抓；更早的抓过一次就够了。
- **详情快照只覆盖抓过的文章**：选更早的分析范围时，完读、分享、关注、画像只统计有快照的那部分。转载 / 旧文没有 appmsg_id，抓不了详情。没有 `send_time` 的（已删除）文章不计入。
- **关注滞后阅读约 1 周**：刚发布文章的关注数不是最终值。
- **粉丝不到 100 时后台不给账号级画像**：读者画像是「推荐占比 ≥ 50%、阅读 ≥ 50」的单篇按阅读加权聚合。
- **分析范围里没有文章时不会覆盖旧结果**：例如最近三个月没发文时选“近3个月”，会提示换范围，上一次的报告和基准保持不变。
- **评分是参考，不是门槛**：有价值但未通过预测的选题仍可保留，最终由我判断。

## 已验证的核心结论（详见最新报告，数字随分析范围浮动）

- **账号核心定位**：科技 / 商业 / 金融。偶尔极少数写社会现象类（须与定位相关）。
- 粉丝 **主要来自文章页**（新增关注渠道饼图只有「文章页关注」一片）；涨粉 ≠ 阅读量，而 = 完读率 × 分享率 × 平台相关度。
- 标题用「具名主体 + 冲突」杠杆约 30×（全量区间）；**周二**发文占阅读一半以上。
- **互动深度**：高阅读 ≠ 高互动（苹果 1915 读互动率 0.6% vs 抖音 405 读互动率 3.7%）。互动率 ≥ 5% 的文章累积推荐权重，写文章要设计互动钩子（提问引留言、金句引收藏、实用引转发）。
- 流量约 90% 来自推荐 → 为推荐优化开篇是关键。
- 里程碑：粉丝满 **100** 后后台自动解锁账号级精准画像。

## 项目结构

```
content/wxpubaccount/
├── backend/
│   ├── config.py       # 路径、账号定位、关键词表、后台地址、抓取参数
│   ├── scraper.py      # Playwright：登录（二维码）、发表记录、总览、详情页，旧快照归档
│   ├── extract_pub.js  # 发表记录页：卡片的标题 / appmsg_id / send_time / 统计数
│   ├── snapshot.py     # 解析页面快照（详情页、用户分析、内容分析）
│   ├── daterange.py    # 口语时段 → 起止日期
│   ├── dataset.py      # 发表记录 → 分析窗口 → 合并详情
│   ├── analysis.py     # 共用口径（标题分类、相关系数、互动、画像）+ 网页数据
│   ├── report.py       # HTML 报告
│   ├── baseline.py     # 爆款预测基准
│   ├── prediction.py   # 标题评分（纯标准库，writing 也按路径加载它）
│   ├── recommend.py    # 选题推荐（热点 RSS + 有效角度 × 开放话题）
│   ├── pipeline.py     # 一次完整分析
│   ├── glossary.py     # 术语解释
│   ├── server.py       # FastAPI
│   └── cli.py          # 命令行
├── frontend/           # 单页应用（原生 JS + ECharts）
├── scripts/
│   ├── start_server.bat / .sh
│   └── probes/probe_snapshots.py
├── .workbuddy/
│   ├── skills/wxpub-analysis/SKILL.md   # 给 AI 助手的操作说明（进 Git）
│   └── memory/                          # 工作日志（本地）
├── data/               # 原始快照、清洗数据、选题推荐、登录态（已 gitignore）
├── reports/            # HTML 报告（已 gitignore）
└── requirements.txt
```

## 版本控制与迁移

- 仓库根 [.gitignore](../../.gitignore) 用 `**/.workbuddy/**` 忽略各项目的 `.workbuddy`，本目录 [.gitignore](./.gitignore) 用 `!.workbuddy/skills/**` 把 SKILL.md 放行，`git add .` 即可。
- `data/`、`reports/`、`.venv/` 不提交。`data/raw/` 是历史时点的原始证据，重新抓取不保证复现旧值，换电脑时要另外同步；`data/processed/` 和报告可以由原始快照随时重建。`data/browser_profile/` 是登录态，不要拷给别人。
- 旧版留下的 `token.txt` 已经用不到，可以删掉。

返回 [内容创作与公众号运营](../README.md)。

# 公众号「一点财知」数据分析工作空间

本工作空间集中保存微信公众号后台的数据抓取产物、分析脚本与创作指引报告。
**所有内容都在本目录内**——换电脑 / 重装只需把整个 `wxpubaccount/` 目录同步过去即可，不依赖 C 盘用户目录。

## 目录结构
```
wxpubaccount/
├── README.md                 # 本说明
├── token.txt                 # 最近一次会话 token（会过期，仅供回溯，每次需重新扫码）
├── reports/                  # 生成的 HTML 报告（带日期 _YYYY-MM-DD 的为最新主报告，可直接双击打开）
├── data/                     # 自动生成的中间数据，git 忽略，可随时删除（重跑 Skill 即再生）
│   ├── raw/                  # 原始快照（.txt）：文章详情 / 发表记录 / 内容·用户分析 / 登录二维码
│   └── processed/            # 清洗后的 JSON（由 raw 派生）
└── .workbuddy/
    ├── skills/wxpub-analysis/  # 分析流水线技能（SKILL.md + scripts/）
    └── memory/                 # 每日工作日志
```

## 如何"定期跑一下分析"（随文章增多重跑）
目标：更快提高**阅读量 + 粉丝数**。

1. 让助手调用 `wxpub-analysis` 技能（或说"定期跑一下分析""复盘数据""怎么涨粉"）。
2. 助手会：扫码登录 → 抓取最新后台数据 → 多轮交叉分析 → 重新生成 `reports/公众号数据分析与创作指引_YYYY-MM-DD.html`。
3. 新文章会自动进入「近 30 天窗口」，报告自动更新，无需你做任何手工整理。

## 脚本（位于 .workbuddy/skills/wxpub-analysis/scripts/）
- `parse_details2.py`：解析 `data/raw/d2_*.txt` 详情页 → `data/processed/article_details2.json`
- `analyze_extra.py`：诊断打印（星期规律 / 标题分级 / 阅读→关注漏斗 / Pearson 相关性）
- `generate_final2.py`：生成带日期的 HTML 报告到 `reports/`

脚本自动从自身位置向上探测到本工作空间根目录，因此在工作空间任意位置调用都能正确读写 `data/` 与 `reports/`。

## 已验证的核心结论（详见 reports/ 最新报告）
- 粉丝 **100% 来自文章页**；涨粉 ≠ 阅读量，而 = 完读率 × 分享率 × 平台相关度。
- 标题用「具名主体 + 冲突」杠杆约 40×；**周二**发文占约 60% 阅读。
- 流量约 91% 来自推荐 → 为推荐优化开篇是关键。
- 里程碑：粉丝满 **100** 后后台自动解锁账号级精准画像（性别/年龄/城市/终端/活跃时间）。

## 版本控制（Git）
仓库根 `D:/Study/Demo/skills`。约定如下：
- **根 `.gitignore` 用 `**/.workbuddy/**`**：默认忽略任意子项目的 `.workbuddy` 内容（守住"不整体移除 .workbuddy 忽略"的意愿；其它项目如 `credit_card` 也照旧受保护）。
- **子项目自行放行 Skill**：`wxpubaccount/.gitignore` 用 `!.workbuddy/skills/` + `!.workbuddy/skills/**` 把本项目的分析技能重新放开。**普通 `git add .` 即可纳入，无需 `git add -f`**。若某子项目没加这条放行规则，它的 `.workbuddy` 就全部默认忽略。
- **自动产物不提交**：`wxpubaccount/.gitignore` 忽略 `data/`、`reports/`、`token.txt`（均可重跑再生；旧报告版本直接删、不进仓库）。
- **报告带日期**：生成器输出 `reports/公众号数据分析与创作指引_YYYY-MM-DD.html`，**看日期最新的一篇即最新报告**（旧版本直接删除，不保留历史副本）。
- 换电脑：`git clone` → Skill 自动到位 → 说"定期跑一下分析" → 重新扫码 → 数据/报告本地重新生成。

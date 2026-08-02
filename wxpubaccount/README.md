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
│   ├── processed/            # 清洗后的 JSON（由 raw 派生，含 hit_baseline.json 爆款预测基准）
│   ├── audit/                # 对抗式审查报告等一次性诊断快照（git 忽略）
│   └── topic_recommendations/ # 选题推荐输出（latest + 带时间戳的 md/json）
└── .workbuddy/
    ├── skills/wxpub-analysis/  # 分析流水线技能（SKILL.md + scripts/，含 predict_hit.py 爆款预测器）
    └── memory/                 # 每日工作日志
```

## 如何"定期跑一下分析"（随文章增多重跑）
目标：围绕账号定位（**科技 / 商业 / 金融**）产出优质内容，提高**阅读量 + 粉丝数**。

1. 让助手调用 `wxpub-analysis` 技能（或说"定期跑一下分析""复盘数据""怎么涨粉"）。
2. 助手会：扫码登录 → 抓取最新后台数据 → 多轮交叉分析（含互动深度）→ 重新生成 `reports/公众号数据分析与创作指引_YYYY-MM-DD.html`，同时自动刷新爆款预测基准。
3. 默认分析**已抓取到的全部发表记录**的文章（当前 82 篇发表记录、76 篇含发文日期，覆盖 2020-06-14 ~ 今天，即账号真实全量——由 `scrape_publish.sh` 自动翻页抓到尾页）；也可指定「近一个月」「2026年至今」或任意时段，报告自动按所选区间更新，无需手工整理。

## 数据范围（可配置）

分析时间范围同时作用于「汇总/星期/幂律分析」与「逐篇详情分析」两个数据源，是**单一窗口**：

| 想要的范围 | 做法（在 `build_articles.py` 阶段控制，下游自动跟随） |
|---|---|
| **已抓取的发表记录（默认）** | 直接跑 `build_articles.py`（不带参数）；或 `--all` / `WXPUB_RANGE=all` |
| **口语指定** | `build_articles.py --nl "近一个月"` / `--nl "2026年至今"` / `--nl "本月"` / `--nl "2026年5月"` / `--nl "2026-05-27 到 2026-07-01"` |
| 最近 N 天 | `WXPUB_WINDOW=N`（如 `WXPUB_WINDOW=90`）；或 `--window N`（仅显式给定才生效） |
| 任意时段 | `WXPUB_SINCE=2026-05-27 WXPUB_UNTIL=2026-07-01`（或 `--since/--until`） |

> 口语短语由 `scripts/resolve_range.py` 解析（已验证：近一个月 / 最近7天 / 近3个月 / 2026年至今 / 今年 / 2026年5月 / 本月 / 上周 / 显式区间）。**无法识别时打印 `WARN` 并回退为已抓取全部**。
>
> 脚本调用示例：
> ```bash
> # 默认=已抓取的全部发表记录
> python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py
> # 口语指定
> python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --nl "近一个月"
> python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --nl "2026年至今"
> # 显式时段
> python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --since 2026-05-27 --until 2026-07-01
> ```
> 报告头部会显示实际数据区间（如 `2020-06-14 ~ 2026-07-17`，取已抓取文章的真实发文区间），区间内的发文篇数、周均、窗口内篇数等也都随范围动态计算，**不再写死某日期或固定篇数**。

⚠️ **重要边界 1（"全部"的范围）**：默认"全部" = `data/raw/publish_p*.txt` 里**已抓取到的发表记录**。`scrape_publish.sh` 会自动翻页（`begin=0,20,40…`）直到某页为空才停，所以默认抓到的就是**账号真实全量**（实测 82 篇发表记录，最早一篇 2020-06-14）。只有极少"已删除"的文章无 `send_time` 会被排除（约 4 篇）。报告头显示的区间是已抓取文章的真实跨度。

⚠️ **重要边界 2（详情快照）**：逐篇详情分析（阅读/完读率/分享/涨粉/画像）依赖 `data/raw/d2_<APPMSGID>.txt` 快照，只覆盖**当初用浏览器抓取过的文章**。因此：
- 选「全部 / 更早时段」时，若那些文章当初没抓详情页，`build_articles` 仍会纳入汇总（星期/幂律/标题分析照常），但详情类章节只显示**已抓取到的那部分**（脚本会打印 `WARN unmatched id` 提示缺快照）；
- 要分析超出已抓取范围的时段，需重新走「步骤 5 逐篇抓详情页」补齐 `d2_*.txt` 后再解析。

## 脚本（位于 .workbuddy/skills/wxpub-analysis/scripts/）
- `parse_details2.py`：解析 `data/raw/d2_*.txt` 详情页 → `data/processed/article_details2.json`（含 reads 统一 + 互动细分：分享/朋友圈/转发/留言/收藏/赞赏/送达/消息阅读/分享产生阅读）
- `analyze_extra.py`：诊断打印（星期规律 / 标题分级 / 阅读→关注漏斗 / Pearson 相关性）
- `generate_final2.py`：生成带日期的 HTML 报告到 `reports/`（11 节，含"互动深度分析"），报告生成后自动调用 update_baseline.py 刷新爆款预测基准
- `update_baseline.py`：从最新数据生成 `data/processed/hit_baseline.json`（爆款预测基准快照，含互动基准 + 账号定位）
- `predict_hit.py`：爆款预测器——输入标题草稿+主题+计划发文日，输出 4 维评分卡（阅读/涨粉/互动/定位匹配）+ 建议
- `recommend_topics.py`：选题推荐器——抓近期热点 RSS + 生成价值型选题，再调用爆款预测器筛出优先可写题，并生成文章大纲

脚本自动从自身位置向上探测到本工作空间根目录，因此在工作空间任意位置调用都能正确读写 `data/` 与 `reports/`。

## 爆款预测（写文章前判断是否值得写）
```bash
python .workbuddy/skills/wxpub-analysis/scripts/predict_hit.py \
  --title "抖音也扛不住了：流量正在杀死好内容" \
  --topics "抖音,流量,内容" \
  --day 周二
```
输出 4 维评分卡：📈阅读爆款潜力 / 💚涨粉潜力 / 🔥互动潜力 / 📍定位匹配（账号定位=科技/商业/金融，偏离时给调整建议）。基准随每次数据复盘自动更新。

## 选题推荐（热点 + 价值方向 + 自动大纲）
```bash
# 默认会抓热点、补价值型方向，并写入 data/topic_recommendations/
python .workbuddy/skills/wxpub-analysis/scripts/recommend_topics.py

# 直接传自然语言需求（推荐这种用法）
python .workbuddy/skills/wxpub-analysis/scripts/recommend_topics.py \
  --ask "给我推荐3个偏实用的微信AI和搜一搜选题，下周二发"

# 自定义热点词与输出数量
python .workbuddy/skills/wxpub-analysis/scripts/recommend_topics.py \
  --queries "微信 AI,微信 搜一搜,OpenAI agent,AI 搜索" \
  --count 6

# 只要价值型方向，不抓热点
python .workbuddy/skills/wxpub-analysis/scripts/recommend_topics.py \
  --ask "给我推荐几个非热点但有长期价值的AI选题" \
  --offline

# 自定义输出目录；若只想打印不落盘，可加 --no-save
python .workbuddy/skills/wxpub-analysis/scripts/recommend_topics.py \
  --output-dir data/topic_recommendations
```

默认输出到 `data/topic_recommendations/`：
- `latest.md` / `latest.json`：最近一次结果；
- `topic_recommendations_YYYYMMDD_HHMMSS.md/json`：按时间归档的历史结果。

推荐器会先做一轮热点过滤，尽量剔除低相关新闻；再把剩余热点改写成“对读者有用”的角度，并补充像“微信搜一搜”这类**非纯热点但高价值**的方向。最终结果分两组：
- **通过爆款预测器的选题**：优先写；
- **未通过预测但值得保留**：会明确标注“未通过爆款预测”。

每个候选题除了预测分，还会直接生成：
- 备选标题
- 写作建议点
- 三段式文章大纲
- 导语草稿 / 正文段落种子 / 结尾草稿
- 素材清单与发文提醒

如果你是在对话里直接说“给我推荐几个选题”，助手也可以直接调用这个脚本的 `--ask` 入口来完成，而不需要你手动拼参数。

## 已验证的核心结论（详见 reports/ 最新报告，数字随区间浮动）
- **账号核心定位**：科技 / 商业 / 金融。偶尔极少数写社会现象类（须与定位相关）。
- 粉丝 **主要来自文章页**（后台快照：新增关注渠道饼图仅 1 片=文章页关注，即 100% 来自文章页；报告内标注抓取日并提示定期复核）；涨粉 ≠ 阅读量，而 = 完读率 × 分享率 × 平台相关度。
- 标题用「具名主体 + 冲突」杠杆约 30–45×（全量区间，随样本浮动）；**周二**发文占阅读主力（全量约 50%+，随分析区间浮动，报告内动态计算）。
- **互动深度**：高阅读≠高互动（苹果 1915 读互动率 0.6% vs 抖音 405 读互动率 3.7%）。高互动文章（分享+留言+收藏）/阅读 ≥5% 累积推荐权重，长远利好。写文章要设计互动钩子（提问引留言、金句引收藏、实用引转发）。
- 流量约 90%+ 来自推荐 → 为推荐优化开篇是关键。
- 里程碑：粉丝满 **100** 后后台自动解锁账号级精准画像（性别/年龄/城市/终端/活跃时间）。

## 版本控制（Git）
仓库根 `D:/Study/Demo/skills`。约定如下：
- **根 `.gitignore` 用 `**/.workbuddy/**`**：默认忽略任意子项目的 `.workbuddy` 内容（守住"不整体移除 .workbuddy 忽略"的意愿；其它项目如 `credit_card` 也照旧受保护）。
- **子项目自行放行 Skill**：`wxpubaccount/.gitignore` 用 `!.workbuddy/skills/` + `!.workbuddy/skills/**` 把本项目的分析技能重新放开。**普通 `git add .` 即可纳入，无需 `git add -f`**。若某子项目没加这条放行规则，它的 `.workbuddy` 就全部默认忽略。
- **自动产物不提交**：`wxpubaccount/.gitignore` 忽略 `data/`、`reports/`、`token.txt`（均可重跑再生；旧报告版本直接删、不进仓库）。
- **报告带日期**：生成器输出 `reports/公众号数据分析与创作指引_YYYY-MM-DD.html`，**看日期最新的一篇即最新报告**（旧版本直接删除，不保留历史副本）。
- 换电脑：`git clone` → Skill 自动到位 → 说"定期跑一下分析" → 重新扫码 → 数据/报告本地重新生成。

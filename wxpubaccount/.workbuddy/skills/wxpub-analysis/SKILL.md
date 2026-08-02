---
name: wxpub-analysis
description: 微信公众平台数据抓取 + 阅读/涨粉分析 + 选题推荐与爆款预测。当用户要分析公众号数据、出创作建议、做选题推荐、或说"定期跑一下分析""复盘数据""帮我看看怎么涨粉/提阅读""给我推荐几个选题"时使用。目标是更快提高阅读量与粉丝数。
---

# 微信公众平台数据分析 Skill（工作空间版）

> **本技能的所有产物都在工作空间内**（报告在 `reports/`、原始快照在 `data/raw/`、清洗后 JSON 在 `data/processed/`、脚本在 `.workbuddy/skills/wxpub-analysis/scripts/`）。**换电脑 / 重装只需把整个工作空间目录同步过去即可**，不依赖 C 盘用户目录。

把"登录后台 → 抓数据 → 多轮交叉分析 → 出自包含 HTML 创作指引报告"的整套流水线封装成本技能，方便随文章增多**定期重跑**。

## 何时用
- 用户要分析公众号（阅读量、涨粉、粉丝画像、创作建议）
- 用户说"定期跑一下分析""复盘数据""出创作指引""怎么涨粉/提阅读"
- 目标：更快提高**阅读量 + 粉丝数**

## ⚠️ 必读坑点（不遵守必翻车）
1. **代理**：本机 Bash 默认带 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7892/`，Chromium 报 `ERR_NO_SUPPORTED_PROXIES`。**每条 `agent-browser` 命令前必须 `unset HTTP_PROXY HTTPS_PROXY`**。
2. **截图语法**：`agent-browser screenshot <path>`（不是 `-o`）。
3. **eval 输出在 STDERR**：捕获用 `$(agent-browser eval "$JS" 2>&1)`；写文件用 `> file 2>&1`（注意顺序，`2>&1 > file` 会得到空文件）。
4. **双编码 JSON**：`agent-browser eval` 返回的字符串是 JSON 字符串的转义串，需 `json.loads()` **两次**才得到真数组。
5. **region 是 list 不是 dict**：`weighted()` 只对 dict 字段（age/gender）用 `.items()`；region 是 `[[name,pct],...]`，要单独处理。
6. **daemon 退化**：约 13+ 次导航后页面返回空。分批（每批 3-4 次导航），进程存活则继续；若退化，重登。
7. **关注滞后阅读约 1 周**：单篇发布的关注在 ~7 天后才累积完，分析"吸粉归因"时要等一周或标注滞后。
8. **账号级画像门槛**：粉丝 <100 时，用户属性（性别/年龄/城市/终端/活跃时间）**全部不展示**（提示"达到100后第二天自动展示"）。此时只能用单篇详情页聚合的画像（样本加权）。这是明确里程碑目标。
9. **阅读大数带千分位逗号**：爆款阅读显示为 `1,925 人`，正则必须用 `[\d,]+` 并 `.replace(",","")` 转 int，否则 `reads` 解析成 `None`（已修 parse_details2.py）。
10. **渠道字段污染**：详情页 `image "X, Y."` 不仅含流量来源，还含「送达人数/消息阅读人数/首次分享人数/总分享人数/分享产生的阅读人数」等完全不同的指标。channels 只保留 `{推荐,搜一搜,公众号主页,公众号消息,其它,聊天会话,朋友圈}`（已修 parse_details2.py）。
11. **小样本画像失真**：粉丝<100 时单篇画像样本极小（2–15 阅读），直接按阅读加权会把噪声放大。聚合读者画像（报告第⑨节）只取「推荐占比≥50% 且 阅读≥50」的高阅读文，排除极低样本（已修 generate_final2.py）。
12. **daemon 退化非硬性**：本机实测连续 17 次详情页导航 + 5 次总览导航未退化。坑点 6 的"~13 次"是经验值、非硬墙；仍建议每批 3–4 篇并批间检查文件非空，退化时重登。

## 目录结构（本工作空间）
```
wxpubaccount/
├── README.md                 # 本工作空间说明
├── token.txt                 # 最近一次会话 token（会过期，仅供回溯）
├── reports/                  # 生成的 HTML 报告（带日期 _YYYY-MM-DD 的为最新主报告，旧版直接删）
├── data/
│   ├── raw/                  # 原始快照：d2_*.txt 详情页、publish_pN.txt 发表记录、
│   │                         #   content_analysis.txt / user_analysis.txt 总览、qr/ 二维码
│   └── processed/            # 清洗后 JSON：article_details.json / article_details2.json /
│                              #   recent_articles.json / _window.json / hit_baseline.json(爆款预测基准)
└── .workbuddy/
    ├── skills/wxpub-analysis/  # 本技能
    │   ├── SKILL.md
    │   └── scripts/            # generate_final2.py / parse_details2.py / analyze_extra.py
    │                         #   build_articles.py / resolve_range.py / extract_pub.js / scrape_publish.sh
    │                         #   update_baseline.py(爆款基准快照) / predict_hit.py(爆款预测器)
    └── memory/                 # 工作日志
```
> 脚本自动从自身位置向上探测到本工作空间根目录，因此无论在哪调用都能正确找到 `data/` 与 `reports/`。也可显式传 `python <script>.py <WORKSPACE_DIR>` 或用环境变量 `WXPUB_DIR`。

## 数据流
```
登录(扫码) → 得 token
  ├─ 内容分析页  → 流量来源结构 + 阅读Top + 阅读总人数   → data/raw/content_analysis.txt
  ├─ 用户分析页  → 每日净增 + 新增关注渠道饼图(验证100%文章页) + [粉丝<100则无账号画像]
                  → data/raw/user_analysis.txt
  ├─ 发表记录页  → 全部文章(appmsg_id + send_time + 标题 + 阅读人数)
                  → data/raw/publish_pN.txt
                  → (scripts/build_articles.py) → data/processed/recent_articles.json(分析窗口内全部)
                                                 → data/processed/article_details.json(同窗口底表)
  └─ 每篇详情页(当前分析窗口) → 阅读/完读率/分享/收藏/留言/单篇新增关注/渠道/年龄/地域/性别
                  → data/raw/d2_<APPMSGID>.txt
        ↓ 解析 (.workbuddy/skills/wxpub-analysis/scripts/parse_details2.py)
        ↓ 统一 reads 口径：从 recent_articles.json 注入【列表页】reads 到所有文章，
        ↓   d2 详情页快照值保留在 reads_d2 字段供回溯（MEMORY 铁律 #4）
        ↓ data/processed/article_details2.json（reads=列表页，reads_d2=详情页快照，详情类字段仅 16 篇有）
        ↓ 多轮交叉分析 (scripts/analyze_extra.py：星期规律/标题分级/阅读→关注漏斗/Pearson相关性)
        ↓ 生成自包含 HTML 报告 (scripts/generate_final2.py → reports/)
```

## 执行步骤

### 1. 登录
```bash
unset HTTP_PROXY HTTPS_PROXY
agent-browser open "https://mp.weixin.qq.com/"      # 直接显示扫码二维码
agent-browser wait 4000
agent-browser screenshot "data/raw/qr/qr.png"        # 呈现给用户扫码
# 用户回复"扫好了"后：
agent-browser eval 'location.href' 2>&1          # 取 token（在 URL 里）
# => https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=TOKEN
# 把 token 写入 token.txt 供本次会话使用
```
记下 `TOKEN`。

### 2. 取菜单真实链接（ref 每次变，必须现取）
```bash
agent-browser eval 'JSON.stringify([...document.querySelectorAll("a")].filter(a=>/分析|属性|增长|发表|内容/.test(a.textContent)).map(a=>({t:a.textContent.trim().slice(0,12),h:a.getAttribute("href")}))' 2>&1
```
得到：发表记录 / 内容分析 / 用户分析 / 菜单分析 等真实 href（含 token）。

### 3. 抓总览（存到 data/raw/）
- **用户分析**：`open <用户分析href>` → 点"用户属性"标签验证粉丝<100 是否仍隐藏；点"用户增长"快照存 `data/raw/user_analysis.txt`；"常读用户分析"看是否"暂无数据"。
- **内容分析**：`open <内容分析href>` → 快照存 `data/raw/content_analysis.txt`（流量来源饼图在 `image "推荐, 91.14."` 这类；阅读总人数在 `StaticText "阅读总人数：3,489人"`）。

### 4. 抓发表记录 → 构造数据清单（存到 data/raw/ + data/processed/）
> **关键**：发表记录页是 SPA，静态快照里没有 `appmsg_id`；且**只有带 `mpunderline` 链接的卡片**才在 DOM 里带 `appmsg_id`/`send_time`，**转载/旧文等卡片链接格式不同，`send_time` 在 DOM 里取不到**。
> 正确做法：`extract_pub.js` 优先读页面**嵌入的 `publish_page` JSON**（`var publish_page = {total_count, publish_list:[...]}`）拿到每篇真实的 `send_time`（`sent_info.time`）与 `appmsg_id`，再用 DOM 兜底。该嵌入 JSON 是**分页**的（每页 20 条），故需逐页抓取。

```bash
# ⚠️ BUG 修复点：发表记录是分页接口（count=20, begin=0,20,40...），必须翻到空页才算抓全。
# 早期版本只抓了前 2 页（假定"共 32 篇"），且 DOM 提取漏掉无 mpunderline 链接卡片的 send_time，
# 导致"全部"成了假全量、最早日期错成 2026-03-14（真实是 2020-06-14）。
# 现用 scrape_publish.sh 自动翻页直到空页，产出 publish_p1..pN.txt：
bash .workbuddy/skills/wxpub-analysis/scripts/scrape_publish.sh <TOKEN>
#   TOKEN 取自登录后 URL 里的 token= 参数（见步骤 2/3）。
#   脚本逐页 open+eval(extract_pub.js)，某页卡片数为 0 时停止并删除该空文件。
#   上限 200 页（4000 篇）封顶防死循环；若命中上限会打印 ⚠️ 警告（绝不静默截断）。
```
> 抓完后 `data/raw/publish_p*.txt` 即账号**真实全部**发表记录（实测 82 篇，最早 2020-06-14）。后续 `build_articles.py` 合并所有页面。
```bash
# 由 publish_pN.txt 构造两个清单 JSON（脚本自动定位 data/ 目录）：
python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py          # 不指定=全部【已抓取】的发表记录
#   → data/processed/recent_articles.json  (分析窗口内全部文章：title/date/reads/appmsg_id)
#   → data/processed/article_details.json  (同窗口底表：id/title/publish，供步骤6合并)
#
# 指定时间范围（口语也能直接传）：
python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --nl "近一个月"
python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --nl "2026年至今"
python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --all     # 等价于不指定
python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py --since 2026-05-27 --until 2026-07-01
```
> 这一步是**本技能早期缺失的胶水环节**——`parse_details2.py` 依赖 `article_details.json` 作底表，但原流程没有脚本生成它。现在由 `build_articles.py` 补齐，skill 才算真正可独立重跑。
> `build_articles.py` 只跳过 `send_time` 为空的卡片（约 4 篇"已删除"文章），`appmsg_id` 为空的（转载/旧文）仍计入聚合分析，仅无逐篇详情快照。

**分析时间范围（同时作用于上面两个文件，单一窗口，可配置）：**
- **默认 = 全部【已抓取】的发表记录**（不指定参数即走全量，范围 = `data/raw/publish_p*.txt` 里的所有卡片；`scrape_publish.sh` 自动翻页到空页，实测 82 张卡片、78 篇含日期，覆盖 **2020-06-14 ~ 今天**）。
  ⚠️ 详情类分析（完读率/分享/涨粉/画像）只覆盖 `data/raw/d2_*.txt` 已抓取快照的 17 篇；要扩到全部文章的逐篇详情，需对更早文章再跑"逐篇抓详情页"。报告头部显示的区间 = 已抓取文章的真实发文区间。
- `--all` / `WXPUB_RANGE=all` → 同默认：已抓取发表记录里的全部卡片。
- `--nl "短语"` → 中文口语短语，由 `resolve_range.py` 解析。常用且已验证：
  `近一个月` / `最近7天` / `近3个月` / `2026年至今` / `今年` / `2026年5月` / `本月` / `上周` / `2026-05-27 到 2026-07-01`；无法识别时打印 `WARN` 并回退为"已抓取全部"。
- `--since/--until` 或 `WXPUB_SINCE/WXPUB_UNTIL`（YYYY-MM-DD）→ 任意显式时段。
- `--window N` / `WXPUB_WINDOW=N`（默认不生效，显式给定才用）→ 最近 N 天。
- 下游 `parse_details2.py` / `generate_final2.py` 自动跟随该范围；报告头部显示实际区间，篇数/周均/窗口篇数均动态计算（不再写死 5.27 / 固定篇数）。
- ⚠️ 逐篇详情只覆盖 `data/raw/d2_*.txt` 已抓取到的文章；选「全部/更早」时若部分文章没抓详情页，`parse_details2` 会打印 `WARN unmatched id`，详情类章节只显示已抓到的部分。需先补抓（步骤5）再解析。

### 5. 逐篇抓详情页（核心，最贵）→ data/raw/d2_<APPMSGID>.txt
详情页 URL（msgid 即 appmsg_id）：
```
https://mp.weixin.qq.com/misc/appmsganalysis?action=detailpage&msgid=<APPMSGID>_1&publish_date=<YYYY-MM-DD>&type=int&pageVersion=1&token=TOKEN&lang=zh_CN
```
对分析窗口内每篇：`open` → `wait 3500` → `snapshot > data/raw/d2_<APPMSGID>.txt`。
**分批 3-4 篇/批**，批间检查文件非空（防 daemon 退化）。

### 6. 解析（用脚本）
```bash
# 在 workspace 根目录执行（脚本会自动定位 data/ 与 reports/）
python .workbuddy/skills/wxpub-analysis/scripts/parse_details2.py
```
从 `data/raw/d2_*.txt` 提取 阅读/完读率/分享/收藏/留言/新增关注/渠道/年龄/地域/性别 → 合并进 `data/processed/article_details2.json`（含派生 share_rate/coll_rate/follow_rate）。

### 7. 多轮分析 + 报告（用脚本）
```bash
python .workbuddy/skills/wxpub-analysis/scripts/analyze_extra.py          # 诊断打印
python .workbuddy/skills/wxpub-analysis/scripts/generate_final2.py        # 产出 reports/公众号数据分析与创作指引_YYYY-MM-DD.html
```
报告含 11 节：发文节奏/星期规律/阅读幂律+标题分级/传播力/**互动深度分析(新)**/阅读→关注漏斗/吸粉归因/涨粉机制+相关性/流量结构/读者画像/可执行优化方向。
报告生成后会**自动调用 `update_baseline.py`** 刷新 `data/processed/hit_baseline.json`（爆款预测基准快照），无需手动跑。

### 7.5 爆款预测（写文章前判断是否值得写）
基于历史数据规律，判断"想写的文章"是否能成爆款。基准快照随每次数据复盘自动更新。

### 7.6 选题推荐（v2 数据驱动，直接一句话让助手给题）
当用户说“给我推荐几个选题”“帮我找几个偏实用/偏长期价值/偏微信生态的方向”时，**优先直接运行**：

```bash
python .workbuddy/skills/wxpub-analysis/scripts/recommend_topics.py \
  --ask "给我推荐3个偏实用的选题，下周二发"
```

**v2 设计原则（用户 2026-07-20 明确）**：
- **话题开放**：不限定在"微信AI/搜一搜"等已验证方向。任何新热点/定位内方向（科技/商业/金融）都能推荐，避免用过去的成功锁死未来的可能性。
- **角度学习**：从历史数据学"什么结构/切口有效"（复盘体 10.2%、方法论 10%、冲突体 9.3% 等互动率高的角度），而非学话题。价值型选题 = 有效角度 × 开放话题。
- **预测器有区分度**：带饱和度惩罚（最近30天写过同主题的扣分），不再是橡皮图章。
- **例外机制生效**：未通过预测但角度好/互动潜力高/定位匹配的也保留，并备注"未通过爆款预测"。

说明：
- `--ask` 支持从自然语言里自动解析：数量、主题方向、是否只看价值型、计划发文日；
- 热点源：Bing/Google News RSS + 36氪/虎嗅/极客公园科技媒体 RSS；
- 检索词动态生成：默认词 + 历史文章高频主题词 + 用户 `--ask` 补充；
- 价值型选题数据驱动：从 `hit_baseline.json` 的 `angle_patterns.effective_angles` 拿有效角度 × 开放话题（热点/未写透方向/定位核心）；
- 每个候选题会给：预测分（含饱和度提醒）、5-8 个备选标题（覆盖8种公式）、写作要点、素材线索、发文提醒；
- 历史推荐去重：和 `data/topic_recommendations/` 已推荐过的标题相似度≥0.7 的自动剔除；
- 结果默认写入 `data/topic_recommendations/`，并同时输出 Markdown/JSON。

如果用户明确说“不要热点/非热点/长期价值”，可附加 `--offline` 或直接把原话放进 `--ask`，脚本会按自然语言偏好自动调整。

```bash
# 命令行：传标题草稿 + 主题关键词 + 计划发文日
python .workbuddy/skills/wxpub-analysis/scripts/predict_hit.py \
  --title "微信这个更新，AI终于扛不住了" \
  --topics "微信,AI,工具" \
  --day 周二

# 交互式（不传参数，逐项输入）
python .workbuddy/skills/wxpub-analysis/scripts/predict_hit.py
```

输出评分卡（4 维度）：
- 📈 **阅读爆款潜力**（0-100）：标题公式分(50) + 时机分(30) + 话题热度(20)
- 💚 **涨粉潜力**（0-100）：平台相关度(40) + 完读分享(30) + 标题时机加权(30)
- 🔥 **互动潜力**（0-20，新增）：方法论→20(高收藏留言) / 冲突→15(高分享) / 复盘→12 / 普通→8。高互动文章累积推荐权重，长远利好。
- 📍 **定位匹配**（新增）：✅ 在定位内 / ⚠️ 偏离定位。账号核心定位=科技/商业/金融，偏离时给调整建议。
- 🎯 综合判断：🌟强烈推荐 / 📈冲阅读但涨粉有限 / 💚阅读不爆但能涨粉 / ⚠️建议调整
- 📚 历史爆款参考 + 💚 历史涨粉参考（从最近数据找相似案例）
- 💡 优化建议（加具名主体/换角度/换日期/回归定位等）

**对话式用法**：用户说"我想写一篇关于 X 的文章"时，助手读 `hit_baseline.json` + 跑 `predict_hit.py`，结合评分卡给出对话建议。

### 8. 清理
```bash
agent-browser close
```
更新 `.workbuddy/memory/YYYY-MM-DD.md`。

## 已验证的核心结论（可直接复用，数字随分析区间浮动，以报告为准）
- **账号核心定位**：科技 / 商业 / 金融。偶尔极少数写社会现象类（须与定位相关）。predict_hit.py 的定位匹配维度会判断是否偏离。
- 粉丝 **主要来自文章页**（用户分析后台快照：新增关注渠道饼图仅 1 片=文章页关注，即 100% 来自文章页；报告内标注抓取日并提示定期在后台复核）。
- 涨阅读：标题「具名主体 + 冲突」杠杆随区间浮动（全量约 30–45×，具名均远高于非具名）；**周二**发文占阅读主力（全量区间约 50%+，随区间浮动，报告内动态计算）。
- 涨粉：**关注 ≠ 阅读量**（r ≈ 0.1–0.2，几乎无关），关注 = 完读率 × 分享率 × 平台相关度（r ≈ 0.4–0.5，最强预测因子）。爆款若与账号定位无关（如纯公司新闻），高阅读也 0 关注；与"科技/商业/金融"相关的高完读高分享文才能转化粉丝。
- **互动深度（新）**：高阅读≠高互动。苹果 1915 读互动率 0.6%（虚胖），抖音 405 读互动率 3.7%（6 倍）。高互动文章（分享+留言+收藏）/阅读 ≥5% 会累积推荐权重，长远利好阅读增长和涨粉。写文章不仅要冲阅读，还要设计互动钩子（提问引留言、金句引收藏、实用引转发）。
- 流量 **约 90%+** 来自推荐（阅读总人数随抓取日变化，报告内动态解析）→ 为推荐优化开篇是关键。
- 口径统一：本报告所有"阅读"= 阅读人数（unique）；reads 字段统一取自【发布列表页】（=用户后台实时看到的值），详情页 d2 快照值保留在 reads_d2 字段供回溯。

## 复用方式
用户下达分析指令时，先确定时间范围再跑：
- "分析一下公众号数据" / "复盘数据" / 没提时段 → **默认=全部已抓取的发表记录**：`build_articles.py`（不带参数）。
- "帮我分析近一个月的公众号文章数据" → `build_articles.py --nl "近一个月"`。
- "帮我分析2026年至今的公众号数据" → `build_articles.py --nl "2026年至今"`。
- "看看 5 月到 7 月的数据" → `build_articles.py --nl "2026-05-01 到 2026-07-31"` 或 `--since/--until`。

识别到口语时段后，在 `build_articles.py` 阶段用 `--nl "短语"`（无法识别则回退为已抓取全部），下游 `parse_details2.py` / `generate_final2.py` 自动跟随。重新扫码登录，token 会变，URL 现取。整个工作空间目录可整体拷贝/同步到任意电脑，无需 C 盘用户目录。

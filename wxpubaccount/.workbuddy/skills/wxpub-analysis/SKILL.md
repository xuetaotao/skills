---
name: wxpub-analysis
description: 微信公众平台数据抓取 + 阅读/涨粉分析与创作指引报告生成。当用户要分析公众号数据、出创作建议、或说"定期跑一下分析""复盘数据""帮我看看怎么涨粉/提阅读"时使用。目标是更快提高阅读量与粉丝数。
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
├── reports/                  # 生成的 HTML 报告（带日期 _YYYY-MM-DD 的为最新主报告）
├── data/
│   ├── raw/                  # 原始快照：d_*.txt / d2_*.txt 详情页、pN.txt 发表记录、
│   │                         #   content_analysis*.txt / user_analysis*.txt 总览、qr/ 二维码
│   ├── processed/            # 清洗后 JSON：article_details*.json / recent_articles.json /
│   │                         #   merged_articles.json / growth_daily.json
│   └── _archive/             # 早期废弃脚本与中间产物（保留备查）
└── .workbuddy/
    ├── skills/wxpub-analysis/  # 本技能
    │   ├── SKILL.md
    │   └── scripts/            # generate_final2.py / parse_details2.py / analyze_extra.py
    │                         #   build_articles.py (发表记录→recent_articles+article_details)
    │                         #   extract_pub.js (发表记录 DOM 提取 eval 片段)
    └── memory/                 # 工作日志
```
> 脚本自动从自身位置向上探测到本工作空间根目录，因此无论在哪调用都能正确找到 `data/` 与 `reports/`。也可显式传 `python <script>.py <WORKSPACE_DIR>` 或用环境变量 `WXPUB_DIR`。

## 数据流
```
登录(扫码) → 得 token
  ├─ 内容分析页  → 流量来源结构 + 阅读Top + 阅读总人数   → data/raw/content_analysis.txt
  ├─ 用户分析页  → 每日净增 + 新增关注渠道饼图(验证100%文章页) + [粉丝<100则无账号画像]
                  → data/raw/user_analysis.txt  → data/processed/growth_daily.json
  ├─ 发表记录页  → 全部文章(appmsg_id + send_time + 标题 + 阅读人数)
                  → data/raw/publish_pN.txt
                  → (scripts/build_articles.py) → data/processed/recent_articles.json(32篇)
                                                 → data/processed/article_details.json(17篇窗口底表)
  └─ 每篇详情页(30天窗口) → 阅读/完读率/分享/收藏/留言/单篇新增关注/渠道/年龄/地域/性别
                  → data/raw/d2_<APPMSGID>.txt
        ↓ 解析 (.workbuddy/skills/wxpub-analysis/scripts/parse_details2.py)
        ↓ data/processed/article_details2.json（含派生 share_rate/coll_rate/follow_rate）
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
```bash
# 翻页抓取（每页 count=20，begin=0,20,... 直到无更多）；每页用 eval 提取卡片
agent-browser open "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?sub=list&begin=0&count=20&token=TOKEN&lang=zh_CN"
agent-browser wait 3500
# 用 scripts/extract_pub.js 提取每篇卡片的 标题 + appmsg_id + send_time(Unix) + 7个统计数，存原始
agent-browser eval "$(cat scripts/extract_pub.js)" > data/raw/publish_p1.txt 2>&1
# 下一页 begin=20 同理 → publish_p2.txt（账号 5.27 起共 32 篇，需 2 页）
```
> **关键**：发表记录页是 SPA，静态快照里没有 `appmsg_id`；必须读 DOM 容器里 `a[href*='mpunderline']` 链接（含 `appmsg_id` 与 `send_time`），卡片类名为 `.weui-desktop-mass-media.weui-desktop-mass-appmsg`。`extract_pub.js` 已封装好。
```bash
# 由 publish_pN.txt 构造两个清单 JSON（脚本自动定位 data/ 目录）：
python .workbuddy/skills/wxpub-analysis/scripts/build_articles.py
#   → data/processed/recent_articles.json  (5.27 起全部 32 篇：title/date/reads/appmsg_id)
#   → data/processed/article_details.json  (30 天窗口 17 篇基础：id/title/publish，供步骤6合并)
```
> 这一步是**本技能早期缺失的胶水环节**——`parse_details2.py` 依赖 `article_details.json` 作底表，但原流程没有脚本生成它。现在由 `build_articles.py` 补齐，skill 才算真正可独立重跑。

### 5. 逐篇抓详情页（核心，最贵）→ data/raw/d2_<APPMSGID>.txt
详情页 URL（msgid 即 appmsg_id）：
```
https://mp.weixin.qq.com/misc/appmsganalysis?action=detailpage&msgid=<APPMSGID>_1&publish_date=<YYYY-MM-DD>&type=int&pageVersion=1&token=TOKEN&lang=zh_CN
```
对 30 天窗口内每篇：`open` → `wait 3500` → `snapshot > data/raw/d2_<APPMSGID>.txt`。
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
报告含 10 节：发文节奏/星期规律/阅读幂律+标题分级/传播力/阅读→关注漏斗/吸粉归因/涨粉机制+相关性/流量结构/读者画像/可执行优化方向。

### 8. 清理
```bash
agent-browser close
```
更新 `.workbuddy/memory/YYYY-MM-DD.md`。

## 已验证的核心结论（可直接复用，2026-07-19 实测）
- 粉丝 **100% 来自文章页**（用户分析：30 天新增 10 人、累计 32，饼图仅 1 片=文章页关注）。
- 涨阅读：标题「具名主体 + 冲突」杠杆 ≈ **43×**（具名均 469 vs 非具名均 11）；**周二**发文占 **60%** 阅读。
- 涨粉：**关注 ≠ 阅读量**（r=**0.17**），关注 = 完读率 × 分享率 × 平台相关度（r=**0.45**）。《苹果》1925 读=0 关注，《微信AI》556 读=4 关注（占文章页关注 40%），《抖音》289 读高互动=0 关注（话题无关）。
- 流量 **91.14%** 来自推荐（阅读总人数 3,489）→ 为推荐优化开篇是关键。
- 口径统一：本报告所有"阅读"= 阅读人数（unique）；recent_articles 与 detail 页同源，避免混用阅读次数/人数。

## 复用方式
用户说"定期跑一下分析"时：直接按上面步骤重跑（重新扫码登录，token 会变，URL 现取）。新文章自动进入 30 天窗口，报告自动更新。整个工作空间目录可整体拷贝/同步到任意电脑，无需 C 盘用户目录。

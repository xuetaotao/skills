---
name: wxpub-analysis
description: 微信公众平台数据抓取 + 阅读/涨粉分析 + 选题推荐与爆款预测。当用户要分析公众号数据、出创作建议、做选题推荐、或说"定期跑一下分析""复盘数据""帮我看看怎么涨粉/提阅读""给我推荐几个选题"时使用。目标是更快提高阅读量与粉丝数。
---

# 公众号数据分析（「一点财知」）

代码在 `content/wxpubaccount/backend/`，下面的命令都在 `content/wxpubaccount/` 目录执行，解释器优先用项目下的 `.venv\Scripts\python.exe`（没有就用 `python`）。完整说明见 [README](../../../README.md)；通用成稿流程见 [写作工作流](../../../../writing/WorkFlow.md)，跨目录写入仍需用户授权。

用户更习惯网页时，直接让他双击 `scripts\start_server.bat`（<http://127.0.0.1:8332>），下面每一步网页上都有对应按钮。

## 按用户的说法选命令

| 用户说 | 执行 |
|---|---|
| 定期跑一下分析 / 复盘数据 / 抓最新数据 | `python -m backend scrape`（弹出浏览器窗口，请用户扫码；登录态保存在 `data/browser_profile/`，没过期就免扫码）。抓完自动按上次的分析范围重新分析 |
| 分析一下（不提时段） | `python -m backend analyze`（= 已抓取的全部文章） |
| 分析近一个月 / 2026年至今 / 5 月到 7 月 | `python -m backend analyze --nl "近一个月"`；或 `--since 2026-05-01 --until 2026-07-31`；或 `--window 90` |
| 我想写 X，能火吗 / 这个标题怎么样 | `python -m backend predict --title "标题" --topics "微信,AI,工具" --day 周二` |
| 给我推荐几个选题 | `python -m backend recommend --ask "用户原话"`；用户说不要热点时加 `--offline` |
| 看看诊断数据 | `python -m backend diagnose` |

`analyze` 产出 `reports/公众号数据分析与创作指引_YYYY-MM-DD.html`（日期最新的是当前报告）和 `data/processed/hit_baseline.json`（爆款预测基准，`predict` / `recommend` 都读它）。`recommend` 结果写到 `data/topic_recommendations/`。

`scrape` 的详情页范围用 `--details`：`missing_recent`（默认：缺详情的 + 近 30 天发表的）、`recent`、`missing`、`all`、`none`。不想弹窗口用 `--headless`，会打开二维码图片让用户扫。

## 必须遵守的口径

1. **阅读量以发表记录列表页为准**（= 后台实时值）；详情页快照的阅读数只放在 `reads_d2` 供回溯，不能两边混用。完读、分享、关注、画像只有详情页有。
2. **原始快照是历史证据**：`data/raw/` 下的文件不要删；重新抓取时被覆盖的旧快照会自动移到 `data/raw/history/<时间>/`。核对关键数字要回到原始快照，不只看 `processed/`。
3. **详情页只覆盖抓过的文章**：选更早的时段时，完读、分享、关注、画像只统计有 `d2_<appmsg_id>.txt` 的文章；需要时用 `scrape --details missing` 补抓。转载 / 旧文没有 appmsg_id，抓不了详情。
4. **关注滞后阅读约 1 周**：刚发布文章的关注数不是最终值，归因时要标注。
5. **粉丝不到 100 时后台不给账号级画像**：读者画像是「推荐占比 ≥ 50%、阅读 ≥ 50」的单篇按阅读加权聚合，样本小，看趋势不看小数点。
6. **评分是参考不是门槛**：未通过预测但角度好、互动潜力高、定位匹配的选题照样保留；选题和定稿由用户决定。账号定位是科技 / 商业 / 金融。
7. 分析范围里一篇文章都没有时，`analyze` 会报错并保留上一次的结果，换个范围即可。

## 页面结构变了怎么办

抓取后若提示「没解析到…，保留上次的快照」或详情页大量失败：

1. `python scripts/probes/probe_snapshots.py` 看现有快照的解析结果；
2. 用 `python -m backend scrape --details none` 只抓总览，打开 `data/raw/user_analysis.txt` / `content_analysis.txt` 看新页面结构；
3. 解析规则在 `backend/snapshot.py`（按「标签 → 后面第一个符合格式的值」取数），发表记录提取在 `backend/extract_pub.js`。

## 收尾

在 `.workbuddy/memory/YYYY-MM-DD.md` 记录本次抓取范围、关键数字和用户新的偏好。

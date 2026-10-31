# 写作工作台

观点型文章的 AI 协作工作流，加一个本地小网站把它用顺手：选阶段、填主题和想法就能拿到完整 Prompt；AI 每给一版就存成新版本，可以逐段对比；定稿前用规则先扫一遍 AI 腔和需要查证的句子；标题可以直接借公众号的爆款预测器打分。

它不是让 AI 从零代写文章，核心原则是：

> 我提供主题、想法、判断和最终取舍；AI 负责拓展、组织、成文、审稿和表达优化。

统一入口见 [内容创作与公众号运营](../README.md)。为公众号写作时，可先参考 [公众号分析](../wxpubaccount/README.md) 的选题建议，发表后再回到那里复盘数据。这里保留通用写作原则，也适用于非公众号文章；账号定位和历史指标不自动替换我的立场。

## 快速开始

```bat
scripts\start_server.bat
```

脚本会启动服务并自动打开 <http://127.0.0.1:8331>。只依赖 `fastapi` 和 `uvicorn`。还没有 `.venv` 时，脚本用 PATH 上的 `python` 创建并安装依赖；已有环境但缺少依赖时，会提示安装命令：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux / macOS 用 `bash scripts/start_server.sh`。不想开网页时，直接打开 [主流程文件](./WorkFlow.md) 和 `prompts/` 下的 Prompt 复制使用即可，两种方式用的是同一套 Prompt。

## 页面

| 页面 | 用途 |
|------|------|
| 写作台 | 五个阶段（观点拓展 / 轻量初稿 / 极简初稿 / 修改反馈 / 质量检查）选一个，填主题、想法、修改意见或正文，下方实时拼好完整 Prompt，一键复制。输入自动记在浏览器里；满意后可「存为新文章」 |
| 文章 | 文章库，按状态（构思 / 初稿 / 修改中 / 定稿 / 已发表）筛选、按标题搜索 |
| 单篇文章 | **正文**：Markdown 编辑 + 预览 + 字数，「保存为新版本」时注明来源（我写的 / AI 初稿 / AI 修改 / 质量检查后）和改了什么，Ctrl+S 保存，离开时提醒未保存的修改；**生成 Prompt**：用这篇的主题、想法和当前正文拼 Prompt；**自检**；**标题评分**：几个候选标题一起打分，一键换成文章标题；**版本**：逐段 / 逐字对比上一版、复制、恢复；**信息**：主题、想法、备注、发表日期和链接 |
| 自检 | 粘贴任意稿子检查：AI 腔套话、绝对化表述、长句长段、刻意排比、破折号和感叹号过多，以及含具体数字、时间、引用来源、公司动态需要查证的句子 |
| 工作流 | 显示 [WorkFlow.md](./WorkFlow.md) |

自检只是规则初筛，引用原话、刻意的修辞都可能被误报；基本满意后仍用「质量检查」Prompt 让 AI 做反方审稿和事实风险扫描。标题评分借用 [公众号分析](../wxpubaccount/README.md) 的爆款预测器和你账号的历史数据（只读，不改那边的文件）；公众号那边还没运行过分析时，这个功能会提示先去分析。评分是参考，不是门槛。

## 文章保存在哪里

```
articles/
└── 2026-10-31_AI_搜索与百度/
    ├── meta.json          # 标题、主题、想法、状态、备注、发表日期和链接、版本列表
    ├── versions/
    │   ├── v001.md        # 每次「保存为新版本」一份，只增不改
    │   └── v002.md
    └── final.md           # 状态改成「定稿」或「已发表」时，当前版本另存一份
```

`articles/` 已 gitignore（文章正文不进这个仓库，另行备份或单独版本管理）；删除文章只是移到 `articles/_trash/`。设置环境变量 `WRITING_ARTICLES_DIR` 可以把文章库放到别处（例如同步盘）。

## 命令行

```bash
python -m backend prompt draft --topic "主题" --ideas "我的想法"     # 打印并复制到剪贴板
python -m backend prompt check --article 2026-10-31_AI_搜索与百度    # 用文章库里的当前版本
python -m backend prompt revise --file draft.md --feedback "第二部分太泛，结尾要收回来"
python -m backend new --title "暂定标题" --topic "主题" --ideas "想法"
python -m backend list
python -m backend save 2026-10-31_AI_搜索与百度 draft.md --source "AI 修改" --note "加强第三部分"
python -m backend check draft.md --title "标题"                     # 或 --article <id>
python -m backend titles "百度也扛不住了" "聊聊 AI 搜索" --topics "百度,AI,搜索"
```

阶段名：`expand` 观点拓展、`draft` 轻量初稿、`quick` 极简初稿、`revise` 修改反馈、`check` 质量检查。

## Prompt 文件

`prompts/` 下的 Markdown 是唯一来源，网页和命令行都只是往里「填空」（主题、我的想法、修改意见各项、正文附在末尾）。要改写法就改这些文件。

| 文件 | 什么时候用 |
|------|------|
| [观点拓展 Prompt](./prompts/观点拓展Prompt.md) | 想法还松散、不确定主线时；先不写正文 |
| [网页端轻量初稿 Prompt](./prompts/网页端轻量初稿Prompt.md) | 常规写作最常用：已有主题和想法，直接写初稿 |
| [极简初稿 Prompt](./prompts/极简初稿Prompt.md) | 想快速看到一版，不想输入太多规则 |
| [修改反馈 Prompt](./prompts/修改反馈Prompt.md) | 初稿出来后按 保留 / 删除 / 加强 / 弱化 提意见 |
| [质量检查 Prompt](./prompts/质量检查Prompt.md) | 基本满意后：反方审稿、事实风险扫描、去 AI 腔 |

## 写作原则

AI 在协作时需要遵守：

1. 保留我的核心观点，不要替换我的立场。
2. 可以适当拓展我的观点，但不要发散太远。
3. 可以提炼概念、补充角度、完善结构。
4. 事实类内容要谨慎，不确定的地方不要写死。
5. 趋势判断要保留边界，不要写成绝对结论。
6. 文章要有自然叙述感和作者感。
7. 不要写成行业报告、白皮书或明显 AI 腔。
8. 修改时要说明改了什么，以及为什么改。
9. 最终审核和定稿由我完成。

## 适合写什么

观点型文章、AI 观察、科技趋势思考、个体机会分析、产品思考、内容创作复盘、认知笔记、长文博客、公众号文章。尤其适合：我已经有一个想法、判断或切入点，但还没有完整结构，AI 帮我拓展、整理、写成初稿，然后我通过多轮反馈审核定稿。

## 项目结构

```
content/writing/
├── WorkFlow.md          # 主流程（日常先看这个）
├── prompts/             # 五个阶段的 Prompt（唯一来源）
├── backend/
│   ├── config.py        # 阶段、状态、路径
│   ├── prompts.py       # 读 Prompt 并填空
│   ├── articles.py      # 文章库与版本
│   ├── checks.py        # 本地自检规则
│   ├── titles.py        # 加载公众号的爆款预测器给标题打分
│   ├── server.py        # FastAPI
│   └── cli.py           # 命令行
├── frontend/            # 单页应用（原生 JS）
├── scripts/start_server.bat / .sh
├── articles/            # 文章（已 gitignore）
└── requirements.txt
```

返回 [内容创作与公众号运营](../README.md)。

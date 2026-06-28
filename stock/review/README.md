# 全球行情复盘汇总

复用 [yupen 鱼盆模型](../../yupen) 的计算结果，把全球主要股市与大宗商品分别汇总成
两张「按偏离度由强到弱」排序的行情表，输出 HTML / Markdown 复盘汇总。

这是行情复盘的第一块：只做**行情汇总**。后续的「重要消息解读」「汇率/国债宏观面板」会在本目录继续扩展。

## 操作说明

### 1. 我自己手动刷新行情汇总

这是最常用的入口，只会刷新鱼盆信号和行情汇总数据：

```bash
# Linux / macOS
bash stock/review/run.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File stock/review/run_windows.ps1
```

运行完成后，重点看：

- `stock/review/outputs/latest_review.html` / `latest_review.md`：完整版行情汇总
- `stock/review/outputs/latest_review_simple.html` / `latest_review_simple.md`：精简版行情汇总

注意：这一步**不会自动生成**“鱼盆模型周度复盘”正文，只会刷新行情数据。

### 2. 交给 AI 生成周度复盘正文

你通常不需要自己按步骤描述“先读什么、再用什么”。直接说下面这种话就够了：

- `帮我生成一下鱼盆模型周度复盘`
- `基于最新 review 输出，生成本周鱼盆模型周度复盘`
- `按 review_preferences 的偏好，写一下这周的鱼盆模型周报`

AI 侧默认应做的事情是：

- 先读取 `stock/review/review_preferences.md`
- 优先使用 `stock/review/outputs/latest_review_simple.md` 作为本周鱼盆数据
- 不主动刷新行情；只有在你明确要求刷新、`latest_review_simple.md` 不存在，或数据日期明显过期时，才先运行行情汇总
- 按当前市场主线生成周报正文

### 3. 什么时候看模板文件

模板和偏好文件主要用于**调整写法**，不是你每次日常运行都要看：

- `stock/review/review_preferences.md`：记录周报写作偏好和新闻筛选偏好
- `stock/review/鱼盆模型周度复盘模版.md`：周报模板，适合改结构或改提示词时查看

## 输出内容

- **📊 全球股市**（一张表，按偏离度排序）：A股宽基 / 美股 / 日经 / 韩国 / 台湾 / 印度 / 英国 / 德国 / 港股
  列：`排名 | 市场 | 名称 | 代码 | 现价 | 涨跌幅 | 临界值(MA20) | 状态 | 偏离度 | 状态转变时间`
- **🏅 大宗商品**（单独一张表，按偏离度排序）：黄金 / 白银 / 铜 / WTI原油 / 布伦特原油
  列同上（无「市场」列）
- **🏦 国债收益率和美元指数**（宏观面板，只取数据日期当日快照，左右并排）：
  - 中美国债收益率（左）：2/5/10/30 年中国 / 美国收益率
  - 美元指数（DXY，右）：现价 + 涨跌幅（居中 KPI 卡片，与左侧表格同为白底风格）
  - 汇率/利率不套鱼盆信号，故不显示 MA20/状态/偏离度等

发生状态转变的标的会高亮为橙色圆角框并标记「⚡今日转变」。
**不含**数据源/PE百分位、操作建议、风险提示，也不含 A股窄基与个股。

每次运行同时生成两个版本：**完整版** 与 **精简版**（每个市场只留代表指数），两者都可在配置里自定义。

## 自定义显示哪些标的

编辑 [`watchlist.py`](watchlist.py)，每个标的有两个开关，改完重新运行即可：

```python
STOCK_DISPLAY = {
    "上证指数":  {"完整版": True,  "精简版": True},
    "上证50":    {"完整版": True,  "精简版": False},  # 完整版显示，精简版隐藏
    ...
}
COMMODITY_DISPLAY = { "COMEX铜": {"完整版": True, "精简版": True}, ... }

# 宏观面板（汇率与利率）：是否显示，两个版本一致
MACRO_DISPLAY = { "美元指数": True, "中美国债": True }
```

- `True` 显示 / `False` 隐藏，两个版本各自独立控制。
- 新增标的 → 加一行即可；未列出的标的：完整版默认显示、精简版默认隐藏。
- 行顺序不影响排名——两个版本始终按偏离度由强到弱排序。

## 运行

依赖（akshare/pandas 等）复用 yupen 的虚拟环境，无需单独安装：

```bash
# Linux / macOS
bash stock/review/run.sh
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File stock/review/run_windows.ps1
# 或直接用 yupen 的解释器
yupen/.venv/bin/python3 stock/review/main.py
```

运行时会实时调用 yupen pipeline 采集并分析最新数据，因此每次都是当前行情。

## 周度复盘补充说明

- 生成“鱼盆模型周度复盘”正文前，应先读取 `stock/review/review_preferences.md`，以该文件作为写作偏好与新闻筛选偏好的优先依据。
- 默认流程是：复用最新 `latest_review_simple.md`，再产出 10 条新闻候选评分表，最后由用户选择 3-5 条写入正文；除非用户明确要求刷新、最新输出不存在或数据明显过期，否则不要先跑行情汇总。
- 新闻候选评分表里的每条新闻应附原文链接，方便用户直接查看原文再做筛选。
- 新闻候选评分表结尾应显式给出“AI 当前已选入复盘周报”的序号，方便用户快速知道 AI 当前实际准备采用哪几条。
- 如果用户已经明确授权“可由 AI 先按偏好自选新闻，若不满意再指出调整”，则可跳过候选表，直接按当期市场主线与 `review_preferences.md` 选择 3-5 条新闻生成正文。
- 周度复盘正文不要把 `latest_review*.md` 里的涨跌幅写成“本周上涨/下跌”；它只是数据日期当日涨跌。

## 输出文件

报告保存在 `stock/review/outputs/`（已 gitignore）：

- `latest_review.html` / `latest_review.md` — 最新·完整版
- `latest_review_simple.html` / `latest_review_simple.md` — 最新·精简版
- `review_YYYYMMDD_HHMMSS.*` / `review_simple_YYYYMMDD_HHMMSS.*` — 带时间戳的历史汇总

## 数据来源说明

| 内容 | 来源 |
|------|------|
| 状态 / 偏离度 / MA20 / 涨跌幅 / 状态转变时间 | yupen 鱼盆模型内存计算结果 |
| 市场分类（market） | yupen 采集层 raw_data |
| 美元指数（DXY）日线 | 新浪 `NewForexService`（DINIW）为主，东财（secid 100.UDI）回退 |
| 中美国债收益率 | akshare `bond_zh_us_rate` |

> - yupen 的 `latest_report.json` 不含 `market` 与状态转变时间，故本模块直接以库方式调用
>   yupen pipeline 取内存完整数据，而非读取其 JSON。
> - 国债/汇率**不进 yupen**：国债是收益率（利率）非价格，套鱼盆 MA20 信号语义相反；
>   美元指数走的是外汇源，与 yupen 指数源不是一套。故这两类在本模块单独取数。

## 项目结构

```
stock/review/
├── main.py          # 入口：采集 → 过滤(完整/精简) → 排序 → 渲染 → 落盘
├── watchlist.py     # ★ 自定义配置：每个标的「完整版/精简版」两个 True/False 开关
├── yupen_source.py  # 调用 yupen pipeline，归一化成扁平行情记录
├── macro.py         # 宏观面板取数：美元指数（新浪/东财）+ 中美国债（akshare）
├── summary.py       # 分组（股市/大宗）、过滤、排序、排名
├── render.py        # HTML / Markdown 渲染（含国旗 SVG）
├── run.sh           # 一键运行 · Linux/macOS（复用 yupen venv）
└── run_windows.ps1  # 一键运行 · Windows（复用 yupen venv）
```

## 免责声明

本汇总仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。

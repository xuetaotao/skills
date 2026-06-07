# 全球行情复盘汇总

复用 [yupen 鱼盆模型](../../yupen) 的计算结果，把全球主要股市与大宗商品分别汇总成
两张「按偏离度由强到弱」排序的行情表，输出 HTML / Markdown 复盘汇总。

这是行情复盘的第一块：只做**行情汇总**。后续的「重要消息解读」「汇率/国债宏观面板」会在本目录继续扩展。

## 输出内容

- **📊 全球股市**（一张表，按偏离度排序）：A股宽基 / 美股 / 日经 / 韩国 / 台湾 / 印度 / 英国 / 德国 / 港股
  列：`排名 | 市场 | 名称 | 代码 | 现价 | 涨跌幅 | 临界值(MA20) | 状态 | 偏离度 | 状态转变时间`
- **🏅 大宗商品**（单独一张表，按偏离度排序）：黄金 / 白银 / 铜 / WTI原油 / 布伦特原油
  列同上（无「市场」列）

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

> yupen 的 `latest_report.json` 不含 `market` 与状态转变时间，故本模块直接以库方式调用
> yupen pipeline 取内存完整数据，而非读取其 JSON。

## 项目结构

```
stock/review/
├── main.py          # 入口：采集 → 过滤(完整/精简) → 排序 → 渲染 → 落盘
├── watchlist.py     # ★ 自定义配置：每个标的「完整版/精简版」两个 True/False 开关
├── yupen_source.py  # 调用 yupen pipeline，归一化成扁平行情记录
├── summary.py       # 分组（股市/大宗）、过滤、排序、排名
├── render.py        # HTML / Markdown 渲染（含国旗 SVG）
├── run.sh           # 一键运行 · Linux/macOS（复用 yupen venv）
└── run_windows.ps1  # 一键运行 · Windows（复用 yupen venv）
```

## 免责声明

本汇总仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。

# 📊 股票策略回测系统

用自然语言描述你的交易策略，系统自动理解并回测，输出收益曲线、绩效指标和基准对比。

## 功能特性

- **自然语言策略**：用中文描述策略，LLM 自动解析为可执行规则
- **多市场支持**：A股指数/个股/ETF、美股、港股（数据源：akshare）
- **丰富指标**：MA/EMA/RSI/MACD/BOLL/ATR 等
- **绩效分析**：年化收益、最大回撤、夏普比率、Alpha/Beta 等
- **可视化**：收益曲线 + 回撤图 + 月度收益热力图
- **基准对比**：支持沪深300、中证500、创业板指等宽基指数对比

## 快速开始

### 一键运行

**Windows**：
```powershell
.\run_windows.ps1
```

**Linux/macOS**：
```bash
chmod +x run.sh
./run.sh
```

脚本会自动创建虚拟环境、安装依赖并启动程序。

### 手动安装

```bash
pip install -r requirements.txt
```

### 交互模式

```bash
cd strategyBacktracking
python -m src
```

按提示输入标的、时间区间和策略描述即可。

### 命令行模式

```bash
# 自然语言策略
python -m src --symbols "510300,510500" --start 2022-01-01 --end 2025-12-31 \
  --strategy "收盘价上穿20日均线买入，跌破20日均线全部卖出"

# 使用规则文件
python -m src --symbols "510300" --start 2022-01-01 --end 2025-12-31 \
  --rules my_strategy.json
```

## 策略描述示例

### 均线趋势策略
```
收盘价站上20日均线时买入，仓位30%；跌破20日均线时全部卖出。
```

### 金字塔加仓策略
```
从高点下跌6.5%首次建仓，每再跌2.5%加仓一次，资金比例1:1:1.5:1.5:2:2:3。
浮盈30%减仓20%，浮盈50%减仓30%。止损8%。
```

### RSI+MACD组合策略
```
RSI低于30且MACD金叉时买入，仓位20%；
RSI高于70或MACD死叉时卖出50%，跌破20日均线清仓。
```

## 输出内容

回测完成后，在 `outputs/` 目录下生成：

```
outputs/
├── backtest_20260507_002350_均线趋势/     # 带时间戳+策略名的目录
│   ├── backtest_20260507_002350_均线趋势_summary.txt
│   ├── backtest_20260507_002350_均线趋势_report.json
│   ├── backtest_20260507_002350_均线趋势_equity_curve.png
│   └── backtest_20260507_002350_均线趋势_monthly_heatmap.png
├── latest_summary.txt                      # 最新报告快捷方式
├── latest_report.json
└── index.html                              # 跳转最新报告
```

## 核心指标

| 指标 | 说明 |
|------|------|
| 年化收益率 | 策略整体回报 |
| 最大回撤 | 最坏情况下的亏损幅度 |
| 夏普比率 | 每承担一份风险获取的回报 |
| 索提诺比率 | 只考虑下行风险的夏普比率 |
| 卡尔玛比率 | 年化收益/最大回撤 |
| Alpha | 超额收益 |
| Beta | 市场敏感度 |
| 胜率 | 盈利交易占比 |
| 盈亏比 | 平均盈利/平均亏损 |

## LLM 配置

系统支持 OpenAI 兼容接口。设置环境变量：

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # 可选
```

或通过命令行参数：

```bash
python -m src --api-key "your-key" --base-url "https://your-api.com/v1"
```

> **注意**：未配置 LLM 时，系统会自动降级为内置关键词匹配解析，支持常见的均线/RSI/MACD/金字塔等策略模式。

## 支持的标的

输入代码或中文名称均可：

| 输入方式 | 示例 |
|---------|------|
| 指数代码 | `000300`、`399006` |
| 带前缀 | `sh000300`、`sz399006` |
| 中文名称 | `沪深300`、`中证500` |
| ETF | `510300`、`510500`、`159915` |
| 个股 | `600519`（贵州茅台） |

## 项目结构

```
strategyBacktracking/
├── src/
│   ├── main.py              # CLI 入口
│   ├── __main__.py          # python -m src 支持
│   ├── config.py            # 系统配置
│   ├── data/                 # 数据层
│   │   ├── fetcher.py        #   akshare 数据获取（多源降级）
│   │   └── cache.py          #   本地 CSV 缓存
│   ├── strategy/            # 策略层
│   │   ├── models.py         #   规则数据模型（Signal/Condition/Action）
│   │   ├── indicators.py     #   技术指标计算（MA/RSI/MACD/BOLL/ATR）
│   │   └── rule_engine.py     #   规则引擎（逐日评估生成信号）
│   ├── llm/                  # LLM 交互层
│   │   ├── parser.py         #   策略解析器（LLM + 降级关键词匹配）
│   │   ├── prompts.py        #   Prompt 模板
│   │   └── validator.py      #   规则校验 & 自动修正
│   ├── engine/               # 回测引擎
│   │   ├── backtester.py     #   核心回测循环
│   │   ├── portfolio.py      #   组合管理（资金/仓位/交易）
│   │   └── trade.py          #   交易记录 & 持仓模型
│   ├── analytics/            # 绩效分析
│   │   ├── metrics.py        #   指标计算（夏普/回撤/Alpha/Beta等）
│   │   └── report.py         #   报告生成（文本+JSON）
│   └── visualization/        # 可视化
│       └── chart.py           #   收益曲线/回撤图/月度热力图
├── outputs/                   # 回测结果输出
├── .gitignore
├── run.sh                     # Linux/macOS 一键运行
├── run_windows.ps1            # Windows 一键运行
├── requirements.txt
└── README.md
```

## 注意事项

- 本工具仅供学习研究，不构成投资建议
- 回测结果不代表未来表现
- 交易成本默认：佣金万2.5 + 印花税千0.5 + 滑点0.1%
- A股 T+1 限制已模拟
- 数据源可能因网络或接口变更而获取失败

## License

MIT

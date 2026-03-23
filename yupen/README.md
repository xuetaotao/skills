# 鱼盆模型量化分析系统

基于鱼盆模型的多Agent量化交易分析系统，自动采集A股主要指数数据，分析趋势强度并生成交易信号。

## 功能特性

- **多数据源采集**：支持新浪财经、中证CSIndex、东方财富、腾讯财经、Baostock等数据源，自动切换备用源；各数据源更新存在延迟，偶尔会出现部分指数已更新、部分未更新的情况，建议收盘后晚间再执行更新
- **多Agent架构**：数据采集、数据分析、信号生成、报告生成四个Agent协同工作
- **鱼盆模型策略**：基于20日均线判断指数强弱状态
- **多格式报告**：支持JSON、Markdown、HTML三种输出格式
- **定时任务**：每日15:30自动执行分析

## 指数列表

- 上证指数 (000001)
- 上证50 (000016)
- 沪深300 (000300)
- 中证A500 (000510)
- 中证500 (000905)
- 中证1000 (000852)
- 中证2000 (932000)
- 创业板指 (399006)
- 科创50 (000688)
- 双创50 (931643)

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install akshare pandas schedule
```

## 使用方法

### 快速运行

```bash
./run.sh
```

### 手动运行

```bash
source .venv/bin/activate
python -m yupen.main
```

### 查看报告

报告文件保存在 `yupen/reports/` 目录下：

- `latest_report.html` - 最新HTML报告（可在浏览器中打开）
- `yupen_report_YYYYMMDD_HHMMSS.json` - JSON格式报告
- `yupen_report_YYYYMMDD_HHMMSS.md` - Markdown格式报告

### 配置指数

编辑 `yupen/config.py` 中的 `INDICES` 列表可添加或修改指数。

### 配置交易时间

编辑 `yupen/config.py` 中的 `REPORT_CONFIG["交易时间"]` 可修改定时任务执行时间。

## 项目结构

```
yupen/
├── __init__.py
├── main.py              # 主程序入口
├── config.py            # 配置文件
├── scheduler.py         # 定时任务调度器
├── orchestrator.py      # 多Agent工作流编排
├── agents/
│   ├── __init__.py
│   ├── base.py          # Agent基类
│   ├── collector.py     # 数据采集Agent
│   ├── analyzer.py      # 数据分析Agent
│   ├── signal_generator.py  # 信号生成Agent
│   └── report_generator.py  # 报告生成Agent
└── reports/             # 报告输出目录
```

## 鱼盆模型说明

鱼盆模型是一种趋势跟随策略：

- **YES状态**：指数价格站上20日均线，看多
- **NO状态**：指数价格跌破20日均线，看空
- **偏离度**：当前价格与MA20的偏离百分比
- **趋势强度排名**：按偏离度从大到小排序

## 免责声明

本系统仅供参考学习，不构成投资建议。股市有风险，投资需谨慎。

"""
鱼盆模型多Agent量化交易系统
Multi-Agent Quantitative Trading System based on Fish Basin Model

架构说明：
- DataCollectorAgent: 数据采集Agent，负责从数据源获取指数数据
- DataAnalyzerAgent: 数据分析Agent，负责计算均线、偏离度、趋势强度
- SignalGeneratorAgent: 信号生成Agent，负责生成交易信号
- ReportAgent: 报告生成Agent，负责汇总结果并生成报告
- MultiAgentOrchestrator: 主调度器，协调各Agent工作
"""

from .agents import (
    DataCollectorAgent,
    DataAnalyzerAgent,
    SignalGeneratorAgent,
    ReportAgent
)
from .orchestrator import MultiAgentOrchestrator

__all__ = [
    'DataCollectorAgent',
    'DataAnalyzerAgent',
    'SignalGeneratorAgent',
    'ReportAgent',
    'MultiAgentOrchestrator'
]

__version__ = '1.0.0'
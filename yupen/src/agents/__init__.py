"""
Agent模块
"""

from .base import BaseAgent
from .collector import DataCollectorAgent
from .analyzer import DataAnalyzerAgent
from .signal_generator import SignalGeneratorAgent
from .report_generator import ReportAgent

__all__ = [
    'BaseAgent',
    'DataCollectorAgent',
    'DataAnalyzerAgent',
    'SignalGeneratorAgent',
    'ReportAgent'
]
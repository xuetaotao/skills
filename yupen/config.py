"""
系统配置
"""

TRADING_CONFIG = {
    "ma_period": 20,
    "ma浮动比例": 0.02,
    "偏移阈值": 0.005,
}

INDICES = [
    {"name": "上证指数", "code": "000001", "market": "sh"},
    {"name": "上证50", "code": "000016", "market": "sh"},
    {"name": "沪深300", "code": "000300", "market": "sh"},
    {"name": "中证A500", "code": "000510", "market": "sh"},
    {"name": "中证500", "code": "000905", "market": "sh"},
    {"name": "中证1000", "code": "000852", "market": "sh"},
    {"name": "中证2000", "code": "932000", "market": "sh"},
    {"name": "创业板指", "code": "399006", "market": "sz"},
    {"name": "科创50", "code": "000688", "market": "sh"},
    {"name": "双创50", "code": "931643", "market": "sh"},
]

REPORT_CONFIG = {
    "交易时间": "15:30",
    "输出格式": ["json", "markdown", "html"],
    "交易信号阈值": {
        "强买入": 0.03,
        "买入": 0.01,
        "观望": 0,
        "谨慎": -0.01,
    }
}
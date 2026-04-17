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
    {"name": "自由现金流指数", "code": "980092", "market": "narrow"},
    {"name": "红利低波指数", "code": "H30269", "market": "narrow"},
    {"name": "工商银行", "code": "601398", "market": "stock"},
    {"name": "农业银行", "code": "601288", "market": "stock"},
    {"name": "粤高速A", "code": "000429", "market": "stock"},
    {"name": "山东高速", "code": "600350", "market": "stock"},
    {"name": "华能水电", "code": "600025", "market": "stock"},
    {"name": "长江电力", "code": "600900", "market": "stock"},
    {"name": "中国广核", "code": "003816", "market": "stock"},
    {"name": "中国移动", "code": "600941", "market": "stock"},
    {"name": "中国电信", "code": "601728", "market": "stock"},
    {"name": "纳斯达克综合指数", "code": ".IXIC", "market": "us"},
    {"name": "标普500", "code": ".INX", "market": "us"},
    {"name": "日经225", "code": "N225", "market": "jp"},
    {"name": "恒生指数", "code": "HSI", "market": "hk"},
    {"name": "恒生科技指数", "code": "HSTECH", "market": "hk"},
    {"name": "伦敦金现", "code": "XAU", "market": "metal"},
    {"name": "伦敦银现", "code": "XAG", "market": "metal"},
    {"name": "WTI原油", "code": "CL", "market": "metal"},
    {"name": "布伦特原油", "code": "OIL", "market": "metal"},
]

REPORT_CONFIG = {
    "交易时间": "19:00",
    "输出格式": ["json", "markdown", "html"],
    "交易信号阈值": {
        "强买入": 0.03,
        "买入": 0.01,
        "观望": 0,
        "谨慎": -0.01,
    },
    "显示PE百分位": True,
    "显示数据源PE指标": True,
}

PE_INDEX_MAP = {
    "上证50": "上证50",
    "沪深300": "沪深300",
    "中证500": "中证500",
    "中证1000": "中证1000",
    "创业板指": "创业板",
    "科创50": "科创50",
    "标普500": "标普500",
    "纳斯达克综合指数": "纳指100",
}

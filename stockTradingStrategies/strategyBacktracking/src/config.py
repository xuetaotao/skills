"""
系统配置
"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
CACHE_DIR = os.path.join(BASE_DIR, ".cache")

# 交易参数
TRADING_CONFIG = {
    "commission_rate": 0.00025,      # 佣金率 万2.5
    "commission_min": 5.0,          # 最低佣金 5元
    "stamp_tax_rate": 0.0005,       # 印花税 千0.5（仅卖出）
    "slippage": 0.001,             # 滑点 0.1%
    "risk_free_rate": 0.02,        # 无风险利率 2%
    "trading_days_per_year": 252,  # 年交易日
}

# 宽基指数映射（用于对比基准）
BENCHMARK_INDICES = {
    "沪深300": {"code": "000300", "market": "sh"},
    "中证500": {"code": "000905", "market": "sh"},
    "创业板指": {"code": "399006", "market": "sz"},
    "上证50": {"code": "000016", "market": "sh"},
    "中证1000": {"code": "000852", "market": "sh"},
    "科创50": {"code": "000688", "market": "sh"},
    "标普500": {"code": ".INX", "market": "us"},
    "纳斯达克100": {"code": ".IXIC", "market": "us"},
    "恒生指数": {"code": "HSI", "market": "hk"},
}

# 常见标的识别映射（用户输入名称 → 代码+市场）
NAME_TO_CODE = {
    # 宽基指数
    "沪深300": {"code": "000300", "market": "sh"},
    "中证500": {"code": "000905", "market": "sh"},
    "中证1000": {"code": "000852", "market": "sh"},
    "上证50": {"code": "000016", "market": "sh"},
    "上证指数": {"code": "000001", "market": "sh"},
    "创业板指": {"code": "399006", "market": "sz"},
    "科创50": {"code": "000688", "market": "sh"},
    # 常见ETF
    "沪深300ETF": {"code": "510300", "market": "sh"},
    "中证500ETF": {"code": "510500", "market": "sh"},
    "创业板ETF": {"code": "159915", "market": "sz"},
    "科创50ETF": {"code": "588000", "market": "sh"},
    "纳指ETF": {"code": "513100", "market": "sh"},
    "标普500ETF": {"code": "513500", "market": "sh"},
    # 常见个股
    "贵州茅台": {"code": "600519", "market": "stock"},
    "宁德时代": {"code": "300750", "market": "stock"},
    "比亚迪": {"code": "002594", "market": "stock"},
    "中国平安": {"code": "601318", "market": "stock"},
    "招商银行": {"code": "600036", "market": "stock"},
    "长江电力": {"code": "600900", "market": "stock"},
    # 海外
    "标普500": {"code": ".INX", "market": "us"},
    "纳斯达克": {"code": ".IXIC", "market": "us"},
    "恒生指数": {"code": "HSI", "market": "hk"},
}

# LLM 配置
LLM_CONFIG = {
    "model": "gpt-4o",
    "temperature": 0.1,
    "max_retries": 3,
}

# 缓存过期时间（秒）
CACHE_EXPIRE_SECONDS = 86400  # 1天

# -*- coding: utf-8 -*-
"""标的清单与参数

精简版（simple）是周报默认使用的版本；网页上可以改，改动保存在数据库里，覆盖这里的默认值。
完整版始终包含全部标的。
"""

MA_PERIOD = 20            # 鱼盆临界值：20 日均线
HISTORY_START = "2015-01-01"
WEEKS = 8                 # 近期走势页默认显示的周数
STALE_DAYS = 4            # 最新数据比整体数据日期落后超过这么多自然日，视为未更新
BIG_MOVE = 0.08           # 单日涨跌超过 8% 在数据健康页提示核对
GAP_DAYS = 10             # 近 120 天内相邻两个交易日间隔超过 10 天视为断档（春节等长假约 7–9 天）

# group 对应周报“市场状态分步解读”的分段
INSTRUMENTS = [
    # code, name, market, region, flag, group, simple
    ("000001", "上证指数", "sh", "A股", "cn", "A股", True),
    ("000016", "上证50", "sh", "A股", "cn", "A股", False),
    ("000300", "沪深300", "sh", "A股", "cn", "A股", True),
    ("000510", "中证A500", "sh", "A股", "cn", "A股", True),
    ("000905", "中证500", "sh", "A股", "cn", "A股", True),
    ("000852", "中证1000", "sh", "A股", "cn", "A股", True),
    ("932000", "中证2000", "sh", "A股", "cn", "A股", True),
    ("399006", "创业板指", "sz", "A股", "cn", "A股", True),
    ("000688", "科创50", "sh", "A股", "cn", "A股", True),
    ("931643", "双创50", "sh", "A股", "cn", "A股", False),
    ("HSI", "恒生指数", "hk", "港股", "hk", "港股", True),
    ("HSTECH", "恒生科技指数", "hk", "港股", "hk", "港股", True),
    (".IXIC", "纳斯达克综合指数", "us", "美股", "us", "美股", True),
    (".INX", "标普500", "us", "美股", "us", "美股", True),
    ("N225", "日经225", "jp", "日本", "jp", "日韩台", True),
    ("KS11", "韩国KOSPI", "kr", "韩国", "kr", "日韩台", True),
    ("TWII", "台湾加权指数", "tw", "台湾", "tw", "日韩台", True),
    ("SENSEX", "印度SENSEX", "in", "印度", "in", "其他海外", False),
    ("UKX", "英国富时100", "uk", "英国", "uk", "其他海外", False),
    ("DAX", "德国DAX30", "de", "德国", "de", "其他海外", False),
    ("XAU", "伦敦金现", "metal", "商品", "", "大宗商品", True),
    ("XAG", "伦敦银现", "metal", "商品", "", "大宗商品", True),
    ("HG", "COMEX铜", "metal", "商品", "", "大宗商品", False),
    ("CL", "WTI原油", "metal", "商品", "", "大宗商品", False),
    ("OIL", "布伦特原油", "metal", "商品", "", "大宗商品", True),
    # 行业与个股：单独成表，不计入股市 / 商品的 YES 统计
    ("980092", "自由现金流指数", "cni", "A股", "cn", "行业与个股", False),
    ("H30269", "红利低波指数", "csi", "A股", "cn", "行业与个股", False),
    ("601398", "工商银行", "stock", "A股", "cn", "行业与个股", False),
    ("601288", "农业银行", "stock", "A股", "cn", "行业与个股", False),
    ("000429", "粤高速A", "stock", "A股", "cn", "行业与个股", False),
    ("600350", "山东高速", "stock", "A股", "cn", "行业与个股", False),
    ("600025", "华能水电", "stock", "A股", "cn", "行业与个股", False),
    ("600900", "长江电力", "stock", "A股", "cn", "行业与个股", False),
    ("003816", "中国广核", "stock", "A股", "cn", "行业与个股", False),
    ("600941", "中国移动", "stock", "A股", "cn", "行业与个股", False),
    ("601728", "中国电信", "stock", "A股", "cn", "行业与个股", False),
]
GROUPS = ["A股", "港股", "美股", "日韩台", "其他海外", "大宗商品", "行业与个股"]


def _kind(market):
    if market == "metal":
        return "commodity"
    return "watch" if market in ("cni", "csi", "stock") else "stock"


INST = {
    c: dict(code=c, name=n, market=m, region=r, flag=f, group=g, simple=s, kind=_kind(m), order=i)
    for i, (c, n, m, r, f, g, s) in enumerate(INSTRUMENTS)
}

# 按偏离度分的 5 档信号（沿用 yupen 日报）：YES 分三档，NO 分两档
SIGNALS = [(0.03, "强力买入"), (0.01, "买入"), (0.0, "观望"), (-0.01, "谨慎"), (None, "卖出")]

# 蛋卷基金估值（PE / PB 历史百分位）：标的代码 → 蛋卷指数代码；参照指数与标的不同的写明参照名称
VALUATION = {
    "000016": ("SH000016", None), "000300": ("SH000300", None), "000905": ("SH000905", None),
    "000852": ("SH000852", None), "399006": ("SZ399006", None), "000688": ("SH000688", None),
    "HSI": ("HKHSI", None), "HSTECH": ("HKHSTECH", None), ".INX": ("SP500", None),
    ".IXIC": ("NDX", "纳指100"), "DAX": ("GDAXI", None), "SENSEX": ("935600", "MSCI印度"),
    "H30269": ("CSIH30269", None),
}

# 宏观序列：美元指数 + 中美国债收益率（收益率单位为 %）
BOND_TERMS = ["2年", "5年", "10年", "30年"]
MACRO = {"DXY": "美元指数"}
for _t in BOND_TERMS:
    MACRO[f"CN{_t}"] = f"中国{_t}期国债收益率"
    MACRO[f"US{_t}"] = f"美国{_t}期国债收益率"

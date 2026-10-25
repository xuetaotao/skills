# -*- coding: utf-8 -*-
"""全局参数与指标注册表。

指标字段直接沿用东方财富 F10「主要指标」接口（RPT_F10_FINANCE_MAINFINADATA）的字段名。
接口按公司类型返回不同的专项字段：银行 / 保险 / 证券 / 通用（一般企业）。
"""

# 首次运行时的默认自选股：国有六大行
DEFAULT_WATCHLIST = ["601398", "601288", "601939", "601988", "601328", "601658"]

# 同行业范围：申万一级不超过 PEER_MAX_L1 家就用一级，否则依次用二级、三级；最多取市值前 PEER_MAX 家
PEER_MAX_L1 = 60
PEER_MAX = 80

VALUATION_START = "2018-01-01"   # 估值历史起点（东方财富估值接口从 2018 年开始）
PRICE_YEARS = 5                   # 区间涨跌幅最长看几年（自选股和同行业都下载这么长的日收盘价）
NEW_DAYS = 7                      # 披露后多少天内标记为“新”
FETCH_WORKERS = 4                 # 财务指标并发请求数
SW_REFRESH_DAYS = 7               # 申万行业分类多少天刷新一次

ORG_TYPES = {"银行": "bank", "保险": "insurance", "证券": "broker", "通用": "general"}
TYPE_NAMES = {"bank": "银行", "insurance": "保险", "broker": "证券", "general": "一般企业"}
ALL = ("bank", "insurance", "broker", "general")

# 报告期月份 → 名称与法定披露截止日（月-日；年报为次年）
PERIODS = {"03-31": ("一季报", "04-30"), "06-30": ("中报", "08-31"), "09-30": ("三季报", "10-31"), "12-31": ("年报", "04-30")}


def M(key, name, unit, types=ALL, group="", better=None, flow=False, digits=2, scale=1, short=None):
    """unit: 亿=元÷1e8；%=字段本身是百分数；x=倍；天；元/股。better: high/low/None。flow=报告期累计的流量，可拆单季。"""
    return dict(key=key, name=name, short=short or name, unit=unit, types=types, group=group, better=better,
                flow=flow, digits=digits, scale=scale)


METRICS = [
    # ---------- 规模与增长（全部类型） ----------
    M("TOTALOPERATEREVE", "营业总收入", "亿", group="规模", flow=True, short="营收"),
    M("TOTALOPERATEREVETZ", "营收同比", "%", group="增长", better="high"),
    M("PARENTNETPROFIT", "归母净利润", "亿", group="规模", flow=True, short="归母净利"),
    M("PARENTNETPROFITTZ", "归母净利同比", "%", group="增长", better="high"),
    M("KCFJCXSYJLR", "扣非净利润", "亿", group="规模", flow=True, short="扣非净利"),
    M("KCFJCXSYJLRTZ", "扣非净利同比", "%", group="增长", better="high"),
    M("DJD_TOI_YOY", "单季营收同比", "%", group="增长", better="high"),
    M("DJD_DPNP_YOY", "单季归母净利同比", "%", group="增长", better="high", short="单季净利同比"),
    # ---------- 盈利 ----------
    M("ROEJQ", "净资产收益率（加权）", "%", group="盈利", better="high", short="ROE"),
    M("XSMLL", "毛利率", "%", ("general",), group="盈利", better="high"),
    M("XSJLL", "净利率", "%", ("general",), group="盈利", better="high"),
    M("ROIC", "投入资本回报率", "%", ("general",), group="盈利", better="high", short="ROIC"),
    M("EPSJB", "基本每股收益", "元", group="每股", digits=3, short="EPS"),
    M("BPS", "每股净资产", "元", group="每股", short="BPS"),
    # ---------- 一般企业：现金流与经营效率 ----------
    M("NCO_NETPROFIT", "经营现金流/净利润", "x", ("general",), group="现金流", better="high", short="现金流/净利"),
    M("JYXJLYYSR", "经营现金流/营收", "%", ("general",), group="现金流", better="high", scale=100, short="现金流/营收"),
    M("ZCFZL", "资产负债率", "%", ("general",), group="偿债", better="low"),
    M("LD", "流动比率", "x", ("general",), group="偿债", better="high"),
    M("YSZKZZTS", "应收账款周转天数", "天", ("general",), group="运营", better="low", digits=1, short="应收周转天数"),
    M("CHZZTS", "存货周转天数", "天", ("general",), group="运营", better="low", digits=1),
    # ---------- 银行 ----------
    M("NET_INTEREST_MARGIN", "净息差", "%", ("bank",), group="息差", better="high"),
    M("NET_INTEREST_SPREAD", "净利差", "%", ("bank",), group="息差", better="high"),
    M("NONPERLOAN", "不良贷款率", "%", ("bank",), group="资产质量", better="low", short="不良率"),
    M("BLDKBBL", "拨备覆盖率", "%", ("bank",), group="资产质量", better="high", short="拨备覆盖"),
    M("LOAN_PROVISION_RATIO", "拨贷比", "%", ("bank",), group="资产质量", better="high"),
    M("HXYJBCZL", "核心一级资本充足率", "%", ("bank",), group="资本", better="high", short="核心一级资本"),
    M("NEWCAPITALADER", "资本充足率", "%", ("bank",), group="资本", better="high"),
    M("GROSSLOANS", "贷款总额", "亿", ("bank",), group="规模", digits=0),
    M("TOTALDEPOSITS", "存款总额", "亿", ("bank",), group="规模", digits=0),
    # ---------- 保险 ----------
    M("EARNED_PREMIUM", "已赚保费", "亿", ("insurance",), group="规模", flow=True),
    M("NBV_LIFE", "寿险新业务价值", "亿", ("insurance",), group="规模", flow=True, short="新业务价值"),
    M("NBV_RATE", "新业务价值率", "%", ("insurance",), group="盈利", better="high"),
    M("NET_ROI", "净投资收益率", "%", ("insurance",), group="投资", better="high"),
    M("TOTAL_ROI", "总投资收益率", "%", ("insurance",), group="投资", better="high"),
    M("SOLVENCY_AR", "综合偿付能力充足率", "%", ("insurance",), group="资本", better="high", short="偿付能力"),
    M("SURRENDER_RATE_LIFE", "寿险退保率", "%", ("insurance",), group="资产质量", better="low"),
    # ---------- 证券 ----------
    M("JZB", "净资本", "亿", ("broker",), group="资本", digits=0),
    M("JZBJZC", "净资本/净资产", "%", ("broker",), group="资本", better="high"),
    M("RISK_COVERAGE", "风险覆盖率", "%", ("broker",), group="资本", better="high"),
    M("CAPITAL_LEVERAGE_RATIO", "资本杠杆率", "%", ("broker",), group="资本", better="high"),
    M("LIQUIDITY_COVERAGE_RATIO", "流动性覆盖率", "%", ("broker",), group="流动性", better="high"),
    M("NET_FUNDING_RATIO", "净稳定资金率", "%", ("broker",), group="流动性", better="high"),
]
METRIC_MAP = {m["key"]: m for m in METRICS}

# 卡片与对比表默认展示的核心指标（按类型）
KEY_METRICS = {
    "bank": ["TOTALOPERATEREVETZ", "PARENTNETPROFITTZ", "ROEJQ", "NET_INTEREST_MARGIN", "NONPERLOAN", "BLDKBBL"],
    "insurance": ["TOTALOPERATEREVETZ", "PARENTNETPROFITTZ", "ROEJQ", "NBV_RATE", "NET_ROI", "SOLVENCY_AR"],
    "broker": ["TOTALOPERATEREVETZ", "PARENTNETPROFITTZ", "ROEJQ", "RISK_COVERAGE", "JZBJZC", "CAPITAL_LEVERAGE_RATIO"],
    "general": ["TOTALOPERATEREVETZ", "PARENTNETPROFITTZ", "ROEJQ", "XSMLL", "NCO_NETPROFIT", "ZCFZL"],
}

# 估值看哪个：金融类看市净率，其余看市盈率
VAL_FOCUS = {"bank": "pb", "insurance": "pb", "broker": "pb", "general": "pe"}

# 区间涨跌幅：(键, 名称, 回看月数；0 = 今年以来，-7 = 7 天)
PERF_PERIODS = [("w1", "近1周", -7), ("m1", "近1月", 1), ("m3", "近3月", 3), ("m6", "近6月", 6), ("ytd", "今年以来", 0),
                ("y1", "近1年", 12), ("y2", "近2年", 24), ("y3", "近3年", 36), ("y5", "近5年", 60)]

# 企业性质：东方财富 F10 的「企业性质」原值 → 大类。按关键词归类，接口新增原值时也能落到合适的类
NATURES = {"central": "央企", "local": "地方国企", "soe": "其他国企", "private": "民企", "foreign": "外资/港澳台", "other": "其他"}


def nature_class(raw):
    """央企子公司 / 中央金融企业 → central；地方国有企业 → local；其他国有企业 → soe；大型民企 / 中小微民企 / 民营企业 → private；
    中外合资、外商独资、港澳台、境外中企 → foreign；其他企业、集体企业 → other。"""
    if not raw:
        return None
    if "央" in raw:
        return "central"
    if "地方国有" in raw:
        return "local"
    if "国有" in raw:
        return "soe"
    if "民" in raw:
        return "private"
    if any(k in raw for k in ("外", "港澳台", "境外")):
        return "foreign"
    return "other"


# 东财「主要指标」接口里要落库的字段（其余字段不存）
STORE_FIELDS = ["REPORT_DATE", "REPORT_TYPE", "REPORT_DATE_NAME", "NOTICE_DATE", "UPDATE_DATE", "ORG_TYPE",
                "SECURITY_NAME_ABBR", "CURRENCY"] + [m["key"] for m in METRICS]

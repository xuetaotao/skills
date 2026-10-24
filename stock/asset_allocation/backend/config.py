# -*- coding: utf-8 -*-
"""资产与数据序列注册表。

两层概念：
- SERIES：数据库里存的原始序列（价格、ETF 股息率、汇率、估值），每个都有数据源和“多久没更新算过期”。
- ASSETS：页面上的投资资产。由价格序列 +（可选）股息率估算 + 汇率换算成人民币计价的总收益序列。

source 取值（取数方式见 fetchers.py）:
  csindex      中证指数官网日线（stock_zh_index_hist_csindex），含全收益指数与债券指数
  sina_index   新浪 A 股指数日线（stock_zh_index_daily）
  yahoo        Yahoo Finance 日线；field=close 原始收盘价 / adjclose 复权价
  yahoo_div    由 Yahoo 的 ETF 分红记录计算的年度股息率
  sina_xau     新浪外盘伦敦金（futures_foreign_hist）
  boc_fx       中国银行人民币牌价（currency_boc_sina），取中行折算价
               中行没有新台币牌价，新台币、韩元用 中行美元折算价 / Yahoo 美元兑该货币 交叉换算（见 FX_SERIES）
  pe_lg        乐咕乐股指数市盈率（月度）
  ebs_lg       乐咕乐股沪深300股债利差（日度）
  bond_cn10y   中国 10 年期国债收益率（bond_zh_us_rate）
"""

START = "2006-11-30"      # 长期统计起点：最晚起步的核心资产（伦敦金）从 2006-10 开始
RF = 0.02                 # 无风险利率（年化），用于夏普比率
WEIGHT_CAP = 0.35         # 最小方差 / 最大夏普 的单资产权重上限
LOOKBACK = 60             # 滚动优化用过去 60 个月估计权重

SERIES = [
    # ===== A 股（中证官网全收益指数，含分红再投资） =====
    dict(code="H00300", name="沪深300全收益", kind="price", source="csindex", symbol="H00300"),
    dict(code="H00905", name="中证500全收益", kind="price", source="csindex", symbol="H00905"),
    dict(code="H00852", name="中证1000全收益", kind="price", source="csindex", symbol="H00852"),
    dict(code="H00922", name="中证红利全收益", kind="price", source="csindex", symbol="H00922"),
    dict(code="A500TR", name="中证A500全收益", kind="price", source="csindex", symbol="000510CNY010"),
    dict(code="SZ399606", name="创业板R（创业板指全收益）", kind="price", source="sina_index", symbol="sz399606"),
    # 科创50、科创创业50 没有可取的全收益指数，用价格指数（两者股息率都不到 1%）
    dict(code="CSI000688", name="科创50", kind="price", source="csindex", symbol="000688"),
    dict(code="CSI931643", name="科创创业50", kind="price", source="csindex", symbol="931643"),
    dict(code="H11001", name="中证全债", kind="price", source="csindex", symbol="H11001"),
    # ===== 海外股票 =====
    dict(code="SP500TR", name="标普500全收益", kind="price", source="yahoo", symbol="^SP500TR", field="close"),
    dict(code="QQQ", name="QQQ（纳指100 ETF）复权价", kind="price", source="yahoo", symbol="QQQ", field="adjclose"),
    dict(code="N225", name="日经225", kind="price", source="yahoo", symbol="^N225", field="close"),
    dict(code="FTSE", name="富时100", kind="price", source="yahoo", symbol="^FTSE", field="close"),
    dict(code="GDAXI", name="德国DAX", kind="price", source="yahoo", symbol="^GDAXI", field="close"),
    dict(code="HSI", name="恒生指数", kind="price", source="yahoo", symbol="^HSI", field="close"),
    dict(code="TWII", name="台湾加权", kind="price", source="yahoo", symbol="^TWII", field="close"),
    dict(code="KS11", name="韩国KOSPI", kind="price", source="yahoo", symbol="^KS11", field="close"),
    # ===== 商品 =====
    dict(code="XAU", name="伦敦金", kind="price", source="sina_xau"),
    # ===== 估算分红用的 ETF 年度股息率 =====
    dict(code="DY_1321T", name="1321.T 股息率（日经225 ETF）", kind="div_yield", source="yahoo_div", symbol="1321.T", freq="Y"),
    dict(code="DY_ISFL", name="ISF.L 股息率（富时100 ETF）", kind="div_yield", source="yahoo_div", symbol="ISF.L", freq="Y"),
    dict(code="DY_2800HK", name="2800.HK 股息率（盈富基金）", kind="div_yield", source="yahoo_div", symbol="2800.HK", freq="Y"),
    dict(code="DY_0050TW", name="0050.TW 股息率（元大台湾50）", kind="div_yield", source="yahoo_div", symbol="0050.TW", freq="Y"),
    dict(code="DY_069500KS", name="069500.KS 股息率（KODEX 200）", kind="div_yield", source="yahoo_div", symbol="069500.KS", freq="Y"),
    # ===== 汇率：1 单位外币 = ? 人民币 =====
    dict(code="FX_USD", name="美元/人民币", kind="fx", source="boc_fx", symbol="美元"),
    dict(code="FX_JPY", name="日元/人民币", kind="fx", source="boc_fx", symbol="日元"),
    dict(code="FX_GBP", name="英镑/人民币", kind="fx", source="boc_fx", symbol="英镑"),
    dict(code="FX_EUR", name="欧元/人民币", kind="fx", source="boc_fx", symbol="欧元"),
    dict(code="FX_HKD", name="港币/人民币", kind="fx", source="boc_fx", symbol="港币"),
    dict(code="USDTWD", name="美元/新台币（Yahoo）", kind="fx", source="yahoo", symbol="TWD=X", field="close"),
    dict(code="USDKRW", name="美元/韩元（Yahoo）", kind="fx", source="yahoo", symbol="KRW=X", field="close"),
    # ===== A 股估值 =====
    dict(code="PE_HS300", name="沪深300 滚动市盈率", kind="valuation", source="pe_lg", symbol="沪深300", freq="M"),
    dict(code="PE_ZZ500", name="中证500 滚动市盈率", kind="valuation", source="pe_lg", symbol="中证500", freq="M"),
    dict(code="PE_ZZ1000", name="中证1000 滚动市盈率", kind="valuation", source="pe_lg", symbol="中证1000", freq="M"),
    dict(code="PE_SZ50", name="上证50 滚动市盈率", kind="valuation", source="pe_lg", symbol="上证50", freq="M"),
    dict(code="PE_CYB50", name="创业板50 滚动市盈率", kind="valuation", source="pe_lg", symbol="创业板50", freq="M"),
    dict(code="EBS_HS300", name="沪深300 股债利差", kind="valuation", source="ebs_lg"),
    dict(code="CN10Y", name="中国10年期国债收益率", kind="valuation", source="bond_cn10y"),
]
for _s in SERIES:
    _s.setdefault("freq", "D")
SERIES_MAP = {s["code"]: s for s in SERIES}

# 超过多少天没有新数据算“过期”。月度估值按月末发布，留出 45 天；年度股息率看当年是否有值。
STALE_DAYS = {"D": 10, "M": 45, "Y": 400}

# group: A股 / 债券 / 海外股票 / 商品；core=True 的资产参与相关性、组合优化和实验室。
# 历史晚于 START 的资产（创业板指、科创50、科创创业50）也可进组合：回测从所选资产都有数据的月份开始，
# 滚动优化在某资产攒够 LOOKBACK 个月数据后才把它纳入候选。
ASSETS = [
    dict(code="CSI300", name="沪深300", group="A股", region="中国", ccy="CNY", price="H00300", basis="全收益指数", core=True),
    dict(code="CSIA500", name="中证A500", group="A股", region="中国", ccy="CNY", price="A500TR",
         basis="全收益指数（2024-09 发布，此前为中证回溯计算）", core=True),
    dict(code="CSI500", name="中证500", group="A股", region="中国", ccy="CNY", price="H00905", basis="全收益指数", core=True),
    dict(code="CSI1000", name="中证1000", group="A股", region="中国", ccy="CNY", price="H00852", basis="全收益指数", core=True),
    dict(code="CSIDIV", name="中证红利", group="A股", region="中国", ccy="CNY", price="H00922", basis="全收益指数", core=True),
    dict(code="CHINEXT", name="创业板指", group="A股", region="中国", ccy="CNY", price="SZ399606",
         basis="全收益指数（创业板R）", core=True),
    dict(code="STAR50", name="科创50", group="A股", region="中国", ccy="CNY", price="CSI000688",
         basis="价格指数（不含分红，股息率约 0.3%）", core=True),
    dict(code="STARGEM50", name="科创创业50", group="A股", region="中国", ccy="CNY", price="CSI931643",
         basis="价格指数（不含分红，股息率约 0.7%）", core=True),
    dict(code="CNBOND", name="中证全债", group="债券", region="中国", ccy="CNY", price="H11001", basis="全收益指数", core=True),
    dict(code="SPX", name="标普500", group="海外股票", region="美国", ccy="USD", price="SP500TR", basis="全收益指数", core=True),
    dict(code="NDX", name="纳指100", group="海外股票", region="美国", ccy="USD", price="QQQ", basis="QQQ 复权价（含分红，已扣费）", core=True),
    dict(code="N225", name="日经225", group="海外股票", region="日本", ccy="JPY", price="N225", div="DY_1321T", basis="价格 + ETF 股息率估算", core=True),
    dict(code="FTSE", name="富时100", group="海外股票", region="英国", ccy="GBP", price="FTSE", div="DY_ISFL", basis="价格 + ETF 股息率估算", core=True),
    dict(code="DAX", name="德国DAX", group="海外股票", region="德国", ccy="EUR", price="GDAXI", basis="全收益指数（DAX 本身含分红）", core=True),
    dict(code="HSI", name="恒生指数", group="海外股票", region="中国香港", ccy="HKD", price="HSI", div="DY_2800HK", basis="价格 + ETF 股息率估算", core=True),
    dict(code="TWII", name="台湾加权", group="海外股票", region="中国台湾", ccy="TWD", price="TWII", div="DY_0050TW", basis="价格 + ETF 股息率估算", core=True),
    dict(code="KOSPI", name="韩国KOSPI", group="海外股票", region="韩国", ccy="KRW", price="KS11", div="DY_069500KS", basis="价格 + ETF 股息率估算", core=True),
    dict(code="GOLD", name="黄金", group="商品", region="全球", ccy="USD", price="XAU", basis="伦敦金现货价格", core=True),
]
ASSET_MAP = {a["code"]: a for a in ASSETS}
CORE = [a["code"] for a in ASSETS if a["core"]]
# 货币 -> 人民币汇率的来源：字符串为直接序列；(a, b) 表示 a / b 交叉
FX_SERIES = {"USD": "FX_USD", "JPY": "FX_JPY", "GBP": "FX_GBP", "EUR": "FX_EUR", "HKD": "FX_HKD",
             "TWD": ("FX_USD", "USDTWD"), "KRW": ("FX_USD", "USDKRW")}

# 示例组合（固定权重，月度再平衡）。只是起点，页面上可以复制后修改。
PRESETS = [
    dict(key="balanced", name="示例·股债金均衡", desc="A 股、海外股票、债券、黄金都有，债券占三分之一左右，适合作为讨论起点。",
         weights={"CSIDIV": .15, "CSI300": .10, "SPX": .15, "NDX": .05, "N225": .05, "HSI": .05, "CNBOND": .35, "GOLD": .10}),
    dict(key="equity_gold", name="示例·全球股票+黄金", desc="原报告中的“均衡配置”：不含债券，股票 80%、黄金 20%。",
         weights={"CSIDIV": .20, "CSI300": .10, "CSI1000": .10, "SPX": .20, "NDX": .10, "N225": .05, "FTSE": .05, "GOLD": .20}),
    dict(key="sixty_forty", name="60/40（沪深300 / 全债）", desc="经典股债六四开，只用 A 股和国内债券。",
         weights={"CSI300": .60, "CNBOND": .40}),
    dict(key="equal", name="等权（长历史资产）", desc="2006 年起就有数据的资产各占相同权重，不做任何判断。"
         "创业板指、科创50、科创创业50 历史较短，不放进来，以免回测区间被缩短。", weights="equal"),
    dict(key="csi300", name="100% 沪深300", desc="单一 A 股基准。", weights={"CSI300": 1.0}),
    dict(key="spx", name="100% 标普500", desc="单一美股基准（人民币计价）。", weights={"SPX": 1.0}),
]
DEFAULT_TARGET = "balanced"


def find_series(code):
    return SERIES_MAP.get(code)

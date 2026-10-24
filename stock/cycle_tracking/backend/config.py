# -*- coding: utf-8 -*-
"""指标注册表与板块结构：全部观测序列的统一定义。

source 取值（取数方式见 fetchers.py）:
  sina_main     新浪国内期货主力连续 (futures_main_sina, 需 symbol)
  sina_foreign  新浪外盘历史 (futures_foreign_hist, 需 symbol)
  westmetall    Westmetall 网站的 LME 官方现货结算价与库存 (需 field 如 LME_Cu_cash，col 取 price / stock)
  eia_crude     EIA 美国原油产量 (macro_usa_crude_inner，接口名易误解，返回的不是库存)
  eia           EIA 官网历史数据表 (需 sid 序列号；scale 为单位换算系数)
  sse           上海航运交易所指数 (需 index)，接口只给当期与上期，靠每次刷新累积
  cn_index      国内指数类 (macro_china_energy_index / macro_china_commodity_price_index, 需 fn)
  sw            申万行业指数 (index_hist_sw, 需 symbol)
  shipping      航运指数 (macro_shipping_bdi/bci/bpi, macro_china_bsi_index/bdti_index, 需 fn)
  ppi_vane      生意社动力煤现货基准价 (100ppi.com 网页抓取)
  ppi_qhd       生意社秦港 Q5500 动力煤报价档案 (100ppi.com 网页抓取，仅 2021-06 ~ 2022-02)
  manual        无免费接口，通过 data/manual.csv 手动补录

role 决定分析语义:
  price      商品价格：分位越高越“热”，用于周期温度与阶段
  inventory  库存：分位高 = 供应宽松；关注去库/累库方向
  supply     供给量（如美国原油产量）
  equity     A 股板块指数：用于股商对照
  freight    运价指数：按价格处理，但允许出现负值（BCI 在 2023 年初确实为负）
  macro      综合指数，仅作背景参考

freq: D 日度 / W 周度，决定多久没更新算“过期”。
archive=True 的序列是已停更的历史档案，只展示，不参与当前判断。
accumulate=True 的序列数据源不提供历史，全量重建时也不清空库里已累积的点。
inv_band: 库存 3 个月变化超过多少 % 算去库 / 累库，默认 10（LME 库存波动大，美国原油库存波动小）。
"""

_WM = dict(source="westmetall")

SERIES = [
    # ===== 有色金属：国内定价 =====
    dict(code="SHFE_CU", name="沪铜主力", sector="metals", unit="元/吨", role="price", source="sina_main", symbol="CU0"),
    dict(code="SHFE_AL", name="沪铝主力", sector="metals", unit="元/吨", role="price", source="sina_main", symbol="AL0"),
    dict(code="SHFE_ZN", name="沪锌主力", sector="metals", unit="元/吨", role="price", source="sina_main", symbol="ZN0"),
    dict(code="SHFE_NI", name="沪镍主力", sector="metals", unit="元/吨", role="price", source="sina_main", symbol="NI0"),
    # ===== 有色金属：国际定价 =====
    dict(code="LME_CU", name="LME铜", sector="metals", unit="美元/吨", role="price", field="LME_Cu_cash", col="price", **_WM),
    dict(code="LME_AL", name="LME铝", sector="metals", unit="美元/吨", role="price", field="LME_Al_cash", col="price", **_WM),
    dict(code="LME_ZN", name="LME锌", sector="metals", unit="美元/吨", role="price", field="LME_Zn_cash", col="price", **_WM),
    dict(code="LME_NI", name="LME镍", sector="metals", unit="美元/吨", role="price", field="LME_Ni_cash", col="price", **_WM),
    dict(code="LME_SN", name="LME锡", sector="metals", unit="美元/吨", role="price", field="LME_Sn_cash", col="price", **_WM),
    dict(code="LME_PB", name="LME铅", sector="metals", unit="美元/吨", role="price", field="LME_Pb_cash", col="price", **_WM),
    dict(code="COMEX_HG", name="COMEX铜", sector="metals", unit="美分/磅", role="price", source="sina_foreign", symbol="HG"),
    # ===== 贵金属（货币属性强，不计入周期温度） =====
    dict(code="XAU", name="伦敦金", sector="metals", unit="美元/盎司", role="price", source="sina_foreign", symbol="XAU"),
    dict(code="XAG", name="伦敦银", sector="metals", unit="美元/盎司", role="price", source="sina_foreign", symbol="XAG"),
    dict(code="COMEX_GC", name="COMEX金", sector="metals", unit="美元/盎司", role="price", source="sina_foreign", symbol="GC"),
    # ===== 有色金属：库存 =====
    *[dict(code=f"LME_STOCK_{m.upper()}", name=f"LME{cn}库存", sector="metals", unit="吨", role="inventory",
           field=f"LME_{m}_cash", col="stock", **_WM)
      for m, cn in (("Cu", "铜"), ("Al", "铝"), ("Zn", "锌"), ("Ni", "镍"), ("Sn", "锡"), ("Pb", "铅"))],
    dict(code="SW_METALS", name="申万有色金属指数", sector="metals", unit="点", role="equity", source="sw", symbol="801050"),
    # ===== 能源：原油 =====
    dict(code="WTI_SPOT", name="WTI现货", sector="energy", unit="美元/桶", role="price", source="eia", sid="RWTC"),
    dict(code="BRENT_SPOT", name="布伦特现货", sector="energy", unit="美元/桶", role="price", source="eia", sid="RBRTE"),
    dict(code="WTI", name="WTI期货", sector="energy", unit="美元/桶", role="price", source="sina_foreign", symbol="CL"),
    dict(code="BRENT", name="布伦特期货", sector="energy", unit="美元/桶", role="price", source="sina_foreign", symbol="OIL"),
    dict(code="INE_SC", name="上海原油SC", sector="energy", unit="元/桶", role="price", source="sina_main", symbol="SC0"),
    dict(code="EIA_STOCK", name="美国商业原油库存", sector="energy", unit="万桶", role="inventory", source="eia",
         sid="WCESTUS1", freq="W", scale=0.1, inv_band=5),
    dict(code="EIA_PROD", name="美国原油产量", sector="energy", unit="万桶/日", role="supply", source="eia_crude", freq="W"),
    # ===== 能源：煤炭 =====
    dict(code="PPI_COAL", name="动力煤现货基准价", sector="energy", unit="元/吨", role="price", source="ppi_vane"),
    dict(code="JM", name="焦煤主力", sector="energy", unit="元/吨", role="price", source="sina_main", symbol="JM0"),
    dict(code="J", name="焦炭主力", sector="energy", unit="元/吨", role="price", source="sina_main", symbol="J0"),
    dict(code="QHD_Q5500", name="秦港Q5500动力煤（21-22档案）", sector="energy", unit="元/吨", role="price",
         source="ppi_qhd", archive=True),
    dict(code="SW_COAL", name="申万煤炭指数", sector="energy", unit="点", role="equity", source="sw", symbol="801950"),
    # ===== 能源：综合指数 =====
    dict(code="CN_ENERGY_IDX", name="中国能源价格综合指数", sector="energy", unit="点", role="macro",
         source="cn_index", fn="macro_china_energy_index"),
    dict(code="CCPI", name="中国大宗商品价格指数", sector="energy", unit="点", role="macro",
         source="cn_index", fn="macro_china_commodity_price_index"),
    # ===== 航运 =====
    dict(code="BDI", name="BDI干散货指数", sector="shipping", unit="点", role="freight", source="shipping", fn="macro_shipping_bdi"),
    dict(code="BCI", name="BCI海岬型指数", sector="shipping", unit="点", role="freight", source="shipping", fn="macro_shipping_bci"),
    dict(code="BPI", name="BPI巴拿马型指数", sector="shipping", unit="点", role="freight", source="shipping", fn="macro_shipping_bpi"),
    dict(code="BSI", name="BSI超灵便型指数", sector="shipping", unit="点", role="freight", source="shipping", fn="macro_china_bsi_index"),
    dict(code="BDTI", name="BDTI原油运输指数", sector="shipping", unit="点", role="freight", source="shipping", fn="macro_china_bdti_index"),
    dict(code="SCFI", name="SCFI集装箱运价指数", sector="shipping", unit="点", role="freight", source="sse", index="scfi",
         freq="W", accumulate=True),
    dict(code="SW_SHIPPING", name="申万航运港口指数", sector="shipping", unit="点", role="equity", source="sw", symbol="801992"),
]

for _s in SERIES:
    _s.setdefault("freq", "D")
    _s.setdefault("archive", False)
    _s.setdefault("accumulate", False)
    if _s["role"] == "inventory":
        _s.setdefault("inv_band", 10)

SERIES_MAP = {s["code"]: s for s in SERIES}

# 数据口径与已知局限，在指标卡片和数据健康页展示
NOTES = {
    "COMEX_HG": "新浪外盘连续合约收盘价，单位美分/磅。只作参考，铜的国际价以 LME 铜为准。",
    "WTI_SPOT": "EIA 公布的库欣 WTI 现货价，通常比期货晚 2–4 天。",
    "BRENT_SPOT": "EIA 公布的布伦特现货价，通常比期货晚 2–4 天。",
    "WTI": "新浪外盘期货连续合约收盘价，更新最及时，与现货有几美元差距。只作参考，温度用现货价。",
    "BRENT": "新浪外盘期货连续合约收盘价，更新最及时，与现货有几美元差距。只作参考，温度用现货价。",
    "EIA_STOCK": "EIA 周报的美国商业原油库存，不含战略储备（SPR），每周三公布上周五的数据。",
    "EIA_PROD": "周度数据，是美国原油产量，库存见「美国商业原油库存」。",
    "PPI_COAL": "2025-08 起才有日度数据，历史分位只基于约 1 年，参考价值有限。",
    "QHD_Q5500": "已停更的历史档案（2021-06 ~ 2022-02），只展示，不参与当前判断。",
    "SCFI": "上海航运交易所只公布当期和上期，每次刷新自动累积；更早的历史可在 data/manual.csv 补录。",
    "SW_SHIPPING": "申万二级行业，2021-12 起。成分以集运、油运和港口为主，与油运指数 BDTI 的周收益相关约 0.3，"
                   "与 BDI 几乎不相关，所以股商对照用 BDTI。",
    "BCI": "2023 年初曾出现负值，属于真实行情。",
    "BDTI": "受地缘冲突、绕航等事件影响大，极端值常由事件驱动。",
    **{f"LME_{m}": "LME 官方现货结算价（Westmetall 整理）。" for m in ("CU", "AL", "ZN", "NI", "SN", "PB")},
    **{f"LME_STOCK_{m}": "LME 注册仓库库存（Westmetall 整理），随官方价每日更新。" for m in ("CU", "AL", "ZN", "NI", "SN", "PB")},
}

# 超过多少天没有新数据算“过期”（日度留出长假余量）
STALE_DAYS = {"D": 10, "W": 21}

# 板块结构：温度 = 各分组温度的平均，避免某类品种数量多就主导结论。
# core: 计算温度/阶段的价格序列；inventory/supply/structure: 辅助信号；equity: 股商对照。
SECTORS = {
    "metals": dict(
        name="有色金属",
        brief="铜、铝等工业金属，跟随全球制造业与基建需求。黄金白银偏货币属性，只作参考，不计入温度。",
        groups=[
            dict(key="copper", name="铜", core=["SHFE_CU", "LME_CU"], inventory="LME_STOCK_CU"),
            dict(key="aluminium", name="铝", core=["SHFE_AL", "LME_AL"], inventory="LME_STOCK_AL"),
        ],
        equity=dict(code="SW_METALS", vs="SHFE_CU"),
    ),
    "energy": dict(
        name="能源",
        brief="原油看全球供需与地缘，煤炭看国内供给与电力需求，两者分开计温后再平均。",
        groups=[
            dict(key="oil", name="原油", core=["WTI_SPOT", "BRENT_SPOT", "INE_SC"], inventory="EIA_STOCK", supply="EIA_PROD"),
            dict(key="coal", name="煤炭", core=["PPI_COAL", "JM"]),
        ],
        equity=dict(code="SW_COAL", vs="JM"),
    ),
    "shipping": dict(
        name="航运",
        brief="干散货运价反映铁矿、煤炭、粮食的贸易需求，油运运价反映原油贸易流向，两者驱动因素不同。",
        groups=[
            dict(key="drybulk", name="干散货", core=["BDI"], structure=["BCI", "BPI", "BSI"]),
            dict(key="tanker", name="油运", core=["BDTI"]),
        ],
        equity=dict(code="SW_SHIPPING", vs="BDTI"),
    ),
}


def find(code):
    return SERIES_MAP.get(code)


def sector_series(sector):
    return [s for s in SERIES if s["sector"] == sector]

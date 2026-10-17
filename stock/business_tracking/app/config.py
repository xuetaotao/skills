# -*- coding: utf-8 -*-
"""指标注册表：全部观测序列的统一定义（代码/名称/板块/单位/数据源）。

source 取值:
  sina_main   新浪国内期货主力连续 (futures_main_sina, 需 symbol)
  sina_foreign 新浪外盘历史 (futures_foreign_hist, 需 symbol)
  lme_stock   LME 库存宽表 (macro_euro_lme_stock, 需 col 取列名)
  eia_crude   EIA 美国原油库存 (macro_usa_crude_inner)
  cn_index    国内指数类 (macro_china_energy_index / macro_china_commodity_price_index, 需 fn)
  sw          申万行业指数 (index_hist_sw, 需 symbol)
  shipping    航运指数 (macro_shipping_bdi/bci/bpi, macro_china_bsi_index/bdti_index, 需 fn)
  manual      无免费接口，通过 data/manual.csv 手动补录
"""

SECTORS = {
    "metals": "有色金属",
    "energy": "能源",
    "shipping": "航运",
}

# 每个板块用于计算周期评分的核心品种（剔除黄金等货币属性品种，避免失真）
SECTOR_CORE = {
    "metals": ["SHFE_CU", "SHFE_AL", "COMEX_HG"],
    "energy": ["WTI", "BRENT", "INE_SC", "PPI_COAL", "JM"],
    "shipping": ["BDI", "BCI", "BPI"],
}

SERIES = [
    # ===== 有色金属：国内定价 =====
    dict(code="SHFE_CU", name="沪铜主力", sector="metals", unit="元/吨", source="sina_main", symbol="CU0"),
    dict(code="SHFE_AL", name="沪铝主力", sector="metals", unit="元/吨", source="sina_main", symbol="AL0"),
    dict(code="SHFE_ZN", name="沪锌主力", sector="metals", unit="元/吨", source="sina_main", symbol="ZN0"),
    dict(code="SHFE_NI", name="沪镍主力", sector="metals", unit="元/吨", source="sina_main", symbol="NI0"),
    # ===== 有色金属：国际定价 =====
    dict(code="XAU", name="伦敦金", sector="metals", unit="美元/盎司", source="sina_foreign", symbol="XAU"),
    dict(code="XAG", name="伦敦银", sector="metals", unit="美元/盎司", source="sina_foreign", symbol="XAG"),
    dict(code="COMEX_GC", name="COMEX金", sector="metals", unit="美元/盎司", source="sina_foreign", symbol="GC"),
    dict(code="COMEX_HG", name="COMEX铜", sector="metals", unit="美分/磅", source="sina_foreign", symbol="HG"),
    dict(code="LME_AL", name="LME铝", sector="metals", unit="美元/吨", source="sina_foreign", symbol="AHD"),
    dict(code="LME_NI", name="LME镍", sector="metals", unit="美元/吨", source="sina_foreign", symbol="NID"),
    dict(code="LME_ZN", name="LME锌", sector="metals", unit="美元/吨", source="sina_foreign", symbol="ZSD"),
    dict(code="LME_SN", name="LME锡", sector="metals", unit="美元/吨", source="sina_foreign", symbol="SND"),
    dict(code="LME_PB", name="LME铅", sector="metals", unit="美元/吨", source="sina_foreign", symbol="PBD"),
    # ===== 有色金属：库存（供应宽松度核心观测） =====
    dict(code="LME_STOCK_CU", name="LME铜库存", sector="metals", unit="吨", source="lme_stock", col="铜"),
    dict(code="LME_STOCK_AL", name="LME铝库存", sector="metals", unit="吨", source="lme_stock", col="铝"),
    dict(code="LME_STOCK_ZN", name="LME锌库存", sector="metals", unit="吨", source="lme_stock", col="锌"),
    dict(code="LME_STOCK_PB", name="LME铅库存", sector="metals", unit="吨", source="lme_stock", col="铅"),
    dict(code="LME_STOCK_NI", name="LME镍库存", sector="metals", unit="吨", source="lme_stock", col="镍"),
    dict(code="LME_STOCK_SN", name="LME锡库存", sector="metals", unit="吨", source="lme_stock", col="锡"),
    dict(code="SW_METALS", name="申万有色金属指数", sector="metals", unit="点", source="sw", symbol="801050"),
    # ===== 能源：原油 =====
    dict(code="WTI", name="WTI原油", sector="energy", unit="美元/桶", source="sina_foreign", symbol="CL"),
    dict(code="BRENT", name="布伦特原油", sector="energy", unit="美元/桶", source="sina_foreign", symbol="OIL"),
    dict(code="INE_SC", name="上海原油SC", sector="energy", unit="元/桶", source="sina_main", symbol="SC0"),
    dict(code="EIA_PROD", name="美国原油产量", sector="energy", unit="万桶/日", source="eia_crude"),
    # ===== 能源：煤炭 =====
    dict(code="JM", name="焦煤主力", sector="energy", unit="元/吨", source="sina_main", symbol="JM0"),
    dict(code="J", name="焦炭主力", sector="energy", unit="元/吨", source="sina_main", symbol="J0"),
    dict(code="PPI_COAL", name="动力煤现货基准价", sector="energy", unit="元/吨", source="ppi_vane"),
    dict(code="QHD_Q5500", name="秦港Q5500动力煤现货(21-22档案)", sector="energy", unit="元/吨", source="ppi_qhd"),
    dict(code="SW_COAL", name="申万煤炭指数", sector="energy", unit="点", source="sw", symbol="801950"),
    # ===== 能源：综合指数 =====
    dict(code="CN_ENERGY_IDX", name="中国能源价格综合指数", sector="energy", unit="点",
         source="cn_index", fn="macro_china_energy_index"),
    dict(code="CCPI", name="中国大宗商品价格指数", sector="energy", unit="点",
         source="cn_index", fn="macro_china_commodity_price_index"),
    # ===== 航运 =====
    dict(code="BDI", name="BDI干散货指数", sector="shipping", unit="点", source="shipping", fn="macro_shipping_bdi"),
    dict(code="BCI", name="BCI海岬型指数", sector="shipping", unit="点", source="shipping", fn="macro_shipping_bci"),
    dict(code="BPI", name="BPI巴拿马型指数", sector="shipping", unit="点", source="shipping", fn="macro_shipping_bpi"),
    dict(code="BSI", name="BSI超灵便型指数", sector="shipping", unit="点", source="shipping", fn="macro_china_bsi_index"),
    dict(code="BDTI", name="BDTI原油运输指数", sector="shipping", unit="点", source="shipping", fn="macro_china_bdti_index"),
    dict(code="SCFI", name="SCFI集装箱运价指数", sector="shipping", unit="点", source="manual"),
]

SERIES_MAP = {s["code"]: s for s in SERIES}


def find(code):
    return SERIES_MAP.get(code)

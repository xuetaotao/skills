# -*- coding: utf-8 -*-
"""实测四大板块核心观测指标的 AKShare 接口：连通性 + 历史深度"""
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

def show(tag, fn):
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f"[{tag}] EMPTY")
            return
        cols = list(df.columns)
        date_col = cols[0]
        first, last = df.iloc[0][date_col], df.iloc[-1][date_col]
        print(f"[{tag}] OK rows={len(df)} cols={cols[:6]} range={first} ~ {last}")
        print(f"    最新行: {df.iloc[-1].to_dict()}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:150]}")
    print()

# === 航运 ===
show("BDI(波罗的海干散货)", lambda: ak.macro_shipping_bdi())
show("BCI(海岬型)", lambda: ak.macro_shipping_bci())
show("BPI(巴拿马型)", lambda: ak.macro_shipping_bpi())
show("BDTI(原油运输)", lambda: ak.macro_china_bdti_index())
show("BSI(超灵便)", lambda: ak.macro_china_bsi_index())
show("中国运价指数(含SCFI)", lambda: ak.macro_china_freight_index())

# === 有色金属 ===
show("LME铜3个月(外盘历史)", lambda: ak.futures_foreign_hist(symbol="LME铜3个月"))
show("沪铜主力连续", lambda: ak.futures_main_sina(symbol="CU0", start_date="20160101", end_date="20260919"))
show("LME库存", lambda: ak.macro_euro_lme_stock())

# === 能源/原油 ===
show("EIA美国原油库存", lambda: ak.macro_usa_api_crude_stock())
show("中国能源价格(东财)", lambda: ak.macro_china_daily_energy())
show("生意社现货价格(近期)", lambda: ak.futures_spot_price_daily(start_day="20260901", end_day="20260919"))

print("done")

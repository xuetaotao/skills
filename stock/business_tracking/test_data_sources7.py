# -*- coding: utf-8 -*-
"""第七轮：A股板块指数（对照分析用）+ 美元指数"""
import akshare as ak
import warnings
warnings.filterwarnings("ignore")

def show(tag, fn):
    try:
        df = fn()
        if df is None or len(df) == 0:
            print(f"[{tag}] EMPTY")
            return
        print(f"[{tag}] OK rows={len(df)} cols={list(df.columns)[:8]}")
        print(f"    head: {df.head(1).to_dict('records')}")
        print(f"    tail: {df.tail(1).to_dict('records')}")
    except Exception as e:
        print(f"[{tag}] FAIL: {type(e).__name__}: {str(e)[:130]}")
    print()

# A股东财行业板块历史
show("东财板块-有色金属", lambda: ak.stock_board_industry_hist_em(
    symbol="有色金属", start_date="20200101", end_date="20260919", period="日k", adjust=""))
show("东财板块-煤炭行业", lambda: ak.stock_board_industry_hist_em(
    symbol="煤炭行业", start_date="20200101", end_date="20260919", period="日k", adjust=""))
show("东财板块-航运港口", lambda: ak.stock_board_industry_hist_em(
    symbol="航运港口", start_date="20200101", end_date="20260919", period="日k", adjust=""))

# 美元指数（新浪全球指数）
show("美元指数(新浪)", lambda: ak.index_global_hist_sina(symbol="DINIW"))
print("done")

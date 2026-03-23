import akshare as ak
import datetime

symbol = "000001"
# Test Sina
try:
    df1 = ak.stock_zh_index_daily(symbol="sh000001")
    print("Sina last date:", df1['date'].iloc[-1])
except Exception as e:
    print("Sina error:", e)

# Test Tencent (stock_zh_index_daily might be the same as sina)
try:
    df2 = ak.stock_zh_index_daily_tx(symbol="sh000001")
    print("Tencent last date:", df2['date'].iloc[-1])
except Exception as e:
    print("Tencent error:", e)

# Test CSIndex
try:
    df3 = ak.stock_zh_index_hist_csindex(symbol="000001")
    if df3 is not None and len(df3) > 0:
        if '日期' in df3.columns:
            print("CSIndex last date:", df3['日期'].iloc[-1])
        elif 'date' in df3.columns:
            print("CSIndex last date:", df3['date'].iloc[-1])
except Exception as e:
    print("CSIndex error:", e)

# Test Baostock
import baostock as bs
bs.login()
try:
    rs = bs.query_history_k_data_plus("sh.000001", "date", start_date="2026-03-20")
    print("Baostock last date:", rs.get_data()['date'].iloc[-1])
except Exception as e:
    print("Baostock error:", e)
bs.logout()


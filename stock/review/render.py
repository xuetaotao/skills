"""HTML / Markdown 渲染

把分组好的行情数据渲染成行情复盘汇总，风格沿用 yupen 报告的配色与卡片感。
"""

from typing import Any, Callable, Dict, List, NamedTuple, Optional

# 内联国旗 SVG（取自 yupen 报告，解决部分系统不渲染国旗 emoji 的问题）
FLAG_SVGS: Dict[str, str] = {
    "cn": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#DE2910"/><polygon points="5,2 6.1,5.5 3,3.3 7,3.3 3.9,5.5" fill="#FFDE00"/><polygon points="10,1 10.4,2.2 9.1,1.5 10.9,1.5 9.6,2.2" fill="#FFDE00"/><polygon points="12,3 12.4,4.2 11.1,3.5 12.9,3.5 11.6,4.2" fill="#FFDE00"/><polygon points="12,6 12.4,7.2 11.1,6.5 12.9,6.5 11.6,7.2" fill="#FFDE00"/><polygon points="10,8 10.4,9.2 9.1,8.5 10.9,8.5 9.6,9.2" fill="#FFDE00"/></svg>',
    "us": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#FFF"/><rect y="0" width="30" height="1.54" fill="#B22234"/><rect y="3.08" width="30" height="1.54" fill="#B22234"/><rect y="6.16" width="30" height="1.54" fill="#B22234"/><rect y="9.24" width="30" height="1.54" fill="#B22234"/><rect y="15.38" width="30" height="1.54" fill="#B22234"/><rect y="18.46" width="30" height="1.54" fill="#B22234"/><rect y="12.3" width="30" height="1.54" fill="#B22234"/><rect width="12" height="10.8" fill="#3C3B6E"/></svg>',
    "jp": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#FFF"/><circle cx="15" cy="10" r="6" fill="#BC002D"/></svg>',
    "kr": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#FFF"/><circle cx="15" cy="10" r="4.8" fill="#CD2E3A"/><path d="M15 5.2a4.8 4.8 0 0 1 0 9.6 2.4 2.4 0 0 1 0-4.8 2.4 2.4 0 0 0 0-4.8z" fill="#0047A0"/><g stroke="#111" stroke-width="1.2"><path d="M6.2 4.2l3.2 2.4M5.4 5.4l3.2 2.4M21.4 12.2l3.2 2.4M20.6 13.4l3.2 2.4M22.9 4.3l-3.2 2.4M24 5.4l-3.2 2.4M8.6 12.2l-3.2 2.4M9.4 13.4l-3.2 2.4"/></g></svg>',
    "tw": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#FE0000"/><rect width="15" height="10" fill="#000095"/><circle cx="7.5" cy="5" r="2.2" fill="#FFF"/><g stroke="#FFF" stroke-width="0.8"><path d="M7.5 1.5v7M4 5h7M5 2.5l5 5M10 2.5l-5 5"/></g></svg>',
    "in": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="6.67" fill="#FF9933"/><rect y="6.67" width="30" height="6.67" fill="#FFF"/><rect y="13.33" width="30" height="6.67" fill="#138808"/><circle cx="15" cy="10" r="2.4" fill="none" stroke="#000080" stroke-width="0.5"/><circle cx="15" cy="10" r="0.5" fill="#000080"/></svg>',
    "uk": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#012169"/><path d="M0,0 30,20 M30,0 0,20" stroke="#FFF" stroke-width="4"/><path d="M0,0 30,20 M30,0 0,20" stroke="#C8102E" stroke-width="2"/><path d="M15,0 V20 M0,10 H30" stroke="#FFF" stroke-width="6"/><path d="M15,0 V20 M0,10 H30" stroke="#C8102E" stroke-width="3.5"/></svg>',
    "de": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="6.67" fill="#000"/><rect y="6.67" width="30" height="6.67" fill="#DD0000"/><rect y="13.33" width="30" height="6.67" fill="#FFCE00"/></svg>',
    "hk": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#DE2910"/><circle cx="15" cy="10" r="4" fill="#FFDE00" stroke="#DE2910" stroke-width="0.5"/><circle cx="15" cy="5.5" r="1.5" fill="#FFDE00"/></svg>',
}


# ----------------------------- 文本格式化 ----------------------------- #

def fmt_price(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--"
    return f"{value:,.2f}"


def fmt_change_text(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--"
    return f"{value * 100:+.2f}%"


def change_class(value: Any) -> str:
    if not isinstance(value, (int, float)) or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"


def deviation_class(record: Dict[str, Any]) -> str:
    value = record.get("deviation")
    if not isinstance(value, (int, float)) or value == 0:
        return "neutral"
    return "positive" if value > 0 else "negative"


# ----------------------------- 列定义 ----------------------------- #

class Column(NamedTuple):
    header: str
    render_html: Callable[[Dict[str, Any]], str]
    render_md: Callable[[Dict[str, Any]], str]


def _name_html(record: Dict[str, Any]) -> str:
    badge = '<span class="change-badge">⚡今日转变</span>' if record.get("changed_today") else ""
    return f'<span class="idx-name">{record["name"]}</span>{badge}'


def _name_md(record: Dict[str, Any]) -> str:
    suffix = " ⚡今日转变" if record.get("changed_today") else ""
    return f'{record["name"]}{suffix}'


def _market_html(record: Dict[str, Any]) -> str:
    flag = FLAG_SVGS.get(record.get("flag", ""), "")
    return f'<span class="region"><span class="flag">{flag}</span>{record.get("region", "")}</span>'


def _status_html(record: Dict[str, Any]) -> str:
    if record.get("status") == "YES":
        return '<span class="status status-yes">✅ YES</span>'
    return '<span class="status status-no">❌ NO</span>'


def _status_md(record: Dict[str, Any]) -> str:
    return "✅ YES" if record.get("status") == "YES" else "❌ NO"


def _change_html(record: Dict[str, Any]) -> str:
    return f'<span class="{change_class(record.get("change"))}">{fmt_change_text(record.get("change"))}</span>'


def _deviation_html(record: Dict[str, Any]) -> str:
    return f'<span class="{deviation_class(record)}">{record.get("deviation_str", "N/A")}</span>'


COL_RANK = Column("排名", lambda r: f'<span class="rank">{r["rank"]}</span>', lambda r: str(r["rank"]))
COL_MARKET = Column("市场", _market_html, lambda r: r.get("region", ""))
COL_NAME = Column("名称", _name_html, _name_md)
COL_CODE = Column("代码", lambda r: f'<code>{r.get("code", "")}</code>', lambda r: f'`{r.get("code", "")}`')
COL_PRICE = Column("现价", lambda r: fmt_price(r.get("price")), lambda r: fmt_price(r.get("price")))
COL_CHANGE = Column("涨跌幅", _change_html, lambda r: fmt_change_text(r.get("change")))
COL_MA = Column("临界值(MA20)", lambda r: fmt_price(r.get("ma20")), lambda r: fmt_price(r.get("ma20")))
COL_STATUS = Column("状态", _status_html, _status_md)
COL_DEVIATION = Column("偏离度", _deviation_html, lambda r: r.get("deviation_str", "N/A"))
COL_CHANGE_DATE = Column("状态转变时间", lambda r: r.get("status_change_date", "") or "--", lambda r: r.get("status_change_date", "") or "--")

STOCK_COLUMNS = [COL_RANK, COL_MARKET, COL_NAME, COL_CODE, COL_PRICE, COL_CHANGE, COL_MA, COL_STATUS, COL_DEVIATION, COL_CHANGE_DATE]
COMMODITY_COLUMNS = [COL_RANK, COL_NAME, COL_CODE, COL_PRICE, COL_CHANGE, COL_MA, COL_STATUS, COL_DEVIATION, COL_CHANGE_DATE]


def fmt_yield(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--"
    return f"{value:.2f}%"


# ----------------------------- HTML 渲染 ----------------------------- #

def _html_table(columns: List[Column], records: List[Dict[str, Any]]) -> str:
    head = "".join(f"<th>{c.header}</th>" for c in columns)
    body_rows = []
    for record in records:
        row_class = " class=\"changed-row\"" if record.get("changed_today") else ""
        cells = "".join(f"<td>{c.render_html(record)}</td>" for c in columns)
        body_rows.append(f"<tr{row_class}>{cells}</tr>")
    if not body_rows:
        body_rows.append(f'<tr><td colspan="{len(columns)}" class="empty">暂无数据</td></tr>')
    return (
        '<table class="review-table">'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
    )


def _bond_table_html(bonds: Dict[str, Any]) -> str:
    cn_flag = f'<span class="flag">{FLAG_SVGS["cn"]}</span>'
    us_flag = f'<span class="flag">{FLAG_SVGS["us"]}</span>'
    rows = []
    for row in bonds["rows"]:
        rows.append(
            f"<tr><td><b>{row['term']}</b></td>"
            f'<td>{fmt_yield(row.get("cn"))}</td>'
            f'<td>{fmt_yield(row.get("us"))}</td></tr>'
        )
    return (
        '<table class="review-table bond-table">'
        f"<thead><tr><th>期限</th><th>{cn_flag} 中国</th><th>{us_flag} 美国</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _usd_card_html(usd: Dict[str, Any]) -> str:
    change = usd.get("change")
    if isinstance(change, (int, float)):
        cls = change_class(change)
        change_html = f'<span class="usd-change {cls}">{fmt_change_text(change)}</span>'
    else:
        change_html = ""
    return (
        '<div class="usd-card">'
        f'<span class="usd-value">{fmt_price(usd.get("price"))}</span>'
        f'{change_html}'
        '<span class="usd-cap">较前一交易日</span>'
        "</div>"
    )


def _macro_html(usd: Optional[Dict[str, Any]], bonds: Optional[Dict[str, Any]]) -> str:
    if not usd and not bonds:
        return ""
    blocks = []
    if bonds:
        blocks.append(
            '<div class="macro-block macro-bonds"><h3>🏛️ 中美国债收益率</h3>'
            f'<div class="table-scroll">{_bond_table_html(bonds)}</div></div>'
        )
    if usd:
        blocks.append(
            '<div class="macro-block macro-usd"><h3>💵 美元指数（DXY）</h3>'
            f'{_usd_card_html(usd)}</div>'
        )
    return f'<div class="card"><h2>🏦 国债收益率和美元指数</h2><div class="macro-grid">{"".join(blocks)}</div></div>'


def render_html(stocks: List[Dict[str, Any]], commodities: List[Dict[str, Any]],
                data_date: str, generated_at: str, title_suffix: str = "",
                usd: Optional[Dict[str, Any]] = None, bonds: Optional[Dict[str, Any]] = None) -> str:
    stock_table = _html_table(STOCK_COLUMNS, stocks)
    commodity_table = _html_table(COMMODITY_COLUMNS, commodities)
    macro_section = _macro_html(usd, bonds)
    title = f"🌍 全球行情复盘汇总{title_suffix}"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #2c2c2c; padding: 24px; }}
.container {{ max-width: 1280px; margin: 0 auto; }}
.page-header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; border-radius: 20px; padding: 28px 32px; box-shadow: 0 10px 30px rgba(102,126,234,0.3); }}
.page-header h1 {{ font-size: 26px; }}
.page-header .meta {{ margin-top: 10px; font-size: 14px; opacity: 0.9; }}
.card {{ background: #fff; border-radius: 18px; padding: 22px 24px; margin-top: 22px; box-shadow: 0 6px 18px rgba(0,0,0,0.06); }}
.card h2 {{ font-size: 19px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }}
.table-scroll {{ overflow-x: auto; }}
.review-table {{ width: 100%; border-collapse: separate; border-spacing: 0 7px; white-space: nowrap; }}
.review-table thead th {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; font-weight: 600; padding: 13px 12px; text-align: left; }}
.review-table thead th:first-child {{ border-radius: 12px 0 0 12px; }}
.review-table thead th:last-child {{ border-radius: 0 12px 12px 0; }}
.review-table tbody td {{ padding: 13px 12px; text-align: left; }}
.review-table tbody tr:not(.changed-row) td {{ box-shadow: inset 0 -1px 0 #f0f0f0; }}
.review-table tbody tr:last-child:not(.changed-row) td {{ box-shadow: none; }}
.review-table tbody tr:hover td {{ background: #f8f9fb; }}
.changed-row td {{ background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-top: 2px solid #ff9800; border-bottom: 2px solid #ff9800; }}
.changed-row td:first-child {{ border-left: 2px solid #ff9800; border-top-left-radius: 12px; border-bottom-left-radius: 12px; }}
.changed-row td:last-child {{ border-right: 2px solid #ff9800; border-top-right-radius: 12px; border-bottom-right-radius: 12px; }}
.rank {{ display: inline-flex; align-items: center; justify-content: center; min-width: 26px; height: 26px; padding: 0 6px; border-radius: 13px; background: #eef0fb; color: #5a4ea2; font-weight: 700; font-size: 13px; }}
.region {{ display: inline-flex; align-items: center; gap: 6px; }}
.flag {{ width: 22px; height: 15px; display: inline-block; border-radius: 2px; overflow: hidden; box-shadow: 0 0 0 1px rgba(0,0,0,0.08); }}
.flag svg {{ width: 100%; height: 100%; display: block; }}
.idx-name {{ font-weight: 600; }}
code {{ background: #f3f4fa; padding: 2px 7px; border-radius: 5px; font-size: 13px; color: #5a4ea2; }}
.status {{ padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }}
.status-yes {{ background: #e8f5e9; color: #2e7d32; }}
.status-no {{ background: #ffebee; color: #c62828; }}
.positive {{ color: #2e7d32; font-weight: 600; }}
.negative {{ color: #c62828; font-weight: 600; }}
.neutral {{ color: #757575; }}
.change-badge {{ display: inline-block; margin-left: 8px; padding: 2px 8px; background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); color: #fff; font-size: 12px; border-radius: 10px; font-weight: 700; }}
.empty {{ text-align: center; color: #999; padding: 24px; }}
.macro-grid {{ display: flex; flex-wrap: wrap; gap: 24px; align-items: stretch; }}
.macro-block {{ display: flex; flex-direction: column; }}
.macro-bonds {{ flex: 1 1 340px; }}
.macro-usd {{ flex: 1 1 240px; }}
.macro-block h3 {{ font-size: 15px; color: #5a4ea2; margin-bottom: 10px; }}
.bond-table {{ width: 100%; }}
.bond-table td, .bond-table th {{ white-space: nowrap; }}
.bond-table tbody td:not(:first-child) {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
.usd-card {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 10px; background: #fff; border: 1px solid #ebe8f6; border-radius: 12px; padding: 24px; box-shadow: 0 4px 14px rgba(102,126,234,0.08); }}
.usd-value {{ font-size: 44px; font-weight: 800; line-height: 1; letter-spacing: 0.5px; color: #4a3f86; font-variant-numeric: tabular-nums; }}
.usd-change {{ font-size: 15px; font-weight: 700; padding: 4px 14px; border-radius: 20px; }}
.usd-change.positive {{ color: #2e7d32; background: #e8f5e9; }}
.usd-change.negative {{ color: #c62828; background: #ffebee; }}
.usd-change.positive::before {{ content: "▲ "; }}
.usd-change.negative::before {{ content: "▼ "; }}
.usd-cap {{ font-size: 12px; color: #9a96b0; }}
.footer {{ margin-top: 22px; text-align: center; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="page-header">
    <h1>{title}</h1>
    <div class="meta">数据日期：{data_date} &nbsp;·&nbsp; 生成时间：{generated_at} &nbsp;·&nbsp; 排序：按偏离度由强到弱</div>
  </div>
  <div class="card">
    <h2>📊 全球股市</h2>
    <div class="table-scroll">{stock_table}</div>
  </div>
  <div class="card">
    <h2>🏅 大宗商品</h2>
    <div class="table-scroll">{commodity_table}</div>
  </div>
  {macro_section}
  <div class="footer">数据来源：鱼盆模型量化分析系统 / akshare / 东方财富 · 本汇总仅供参考，不构成投资建议</div>
</div>
</body>
</html>"""


# ----------------------------- Markdown 渲染 ----------------------------- #

def _md_table(columns: List[Column], records: List[Dict[str, Any]]) -> str:
    header = "| " + " | ".join(c.header for c in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, divider]
    if not records:
        lines.append("| " + " | ".join("--" for _ in columns) + " |")
    for record in records:
        lines.append("| " + " | ".join(c.render_md(record) for c in columns) + " |")
    return "\n".join(lines)


def _macro_md(usd: Optional[Dict[str, Any]], bonds: Optional[Dict[str, Any]]) -> str:
    if not usd and not bonds:
        return ""
    parts = ["## 🏦 国债收益率和美元指数\n"]
    if bonds:
        parts.append("**🏛️ 中美国债收益率**\n")
        lines = ["| 期限 | 🇨🇳 中国 | 🇺🇸 美国 |", "| --- | --- | --- |"]
        for row in bonds["rows"]:
            lines.append(f"| {row['term']} | {fmt_yield(row.get('cn'))} | {fmt_yield(row.get('us'))} |")
        parts.append("\n".join(lines) + "\n")
    if usd:
        change = usd.get("change")
        chg = fmt_change_text(change) if isinstance(change, (int, float)) else "--"
        parts.append(f"**💵 美元指数（DXY）**：{fmt_price(usd.get('price'))}（{chg}，较前一交易日）\n")
    return "\n".join(parts) + "\n"


def render_markdown(stocks: List[Dict[str, Any]], commodities: List[Dict[str, Any]],
                    data_date: str, generated_at: str, title_suffix: str = "",
                    usd: Optional[Dict[str, Any]] = None, bonds: Optional[Dict[str, Any]] = None) -> str:
    return (
        f"# 🌍 全球行情复盘汇总{title_suffix}\n\n"
        f"> 数据日期：{data_date} · 生成时间：{generated_at} · 排序：按偏离度由强到弱\n\n"
        "## 📊 全球股市\n\n"
        f"{_md_table(STOCK_COLUMNS, stocks)}\n\n"
        "## 🏅 大宗商品\n\n"
        f"{_md_table(COMMODITY_COLUMNS, commodities)}\n\n"
        f"{_macro_md(usd, bonds)}"
        "---\n\n"
        "数据来源：鱼盆模型量化分析系统 / akshare / 东方财富 · 本汇总仅供参考，不构成投资建议\n"
    )

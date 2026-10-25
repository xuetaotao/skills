# -*- coding: utf-8 -*-
"""行情复盘汇总：截图版 HTML 与 AI 素材 Markdown

HTML 用于周报截图，也是 GitHub Pages 上的日报；Markdown 在表格之后追加“本周变化”，供 AI 写周报。
完整版额外带“信号”和“PE 百分位”两列，精简版保持周报截图的样子。
"""
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from . import analytics
from .config import INST, SIGNALS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(BASE, "outputs")
SOURCES = "新浪财经 / 中证指数 / 国证指数 / 台湾证交所 / 东方财富 / 腾讯财经 / 蛋卷基金 / akshare"

# 内联国旗 SVG，解决部分系统不渲染国旗 emoji 的问题
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


def _badge(record: Dict[str, Any]) -> str:
    if record.get("changed_today"):
        return "⚡今日转变"
    if record.get("changed_week"):
        return "🔄本周转变"
    return ""


def _name_html(record: Dict[str, Any]) -> str:
    b = _badge(record)
    badge = f'<span class="change-badge{" week" if b.startswith("🔄") else ""}">{b}</span>' if b else ""
    stale = f'<span class="stale-badge">数据截至 {record["status_date"][5:]}</span>' if record.get("stale") else ""
    return f'<span class="idx-name">{record["name"]}</span>{badge}{stale}'


def _name_md(record: Dict[str, Any]) -> str:
    b = _badge(record)
    stale = f" ⚠️数据截至{record['status_date']}" if record.get("stale") else ""
    return f'{record["name"]}{" " + b if b else ""}{stale}'


def _market_html(record: Dict[str, Any]) -> str:
    flag = FLAG_SVGS.get(record.get("flag", ""), "")
    return f'<span class="region"><span class="flag">{flag}</span>{record.get("region", "")}</span>'


def _status_html(record: Dict[str, Any]) -> str:
    if record.get("status") == "YES":
        return '<span class="status status-yes">YES</span>'
    return '<span class="status status-no">NO</span>'


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

SIGNAL_CLASS = {label: f"sig{i}" for i, (_t, label) in enumerate(SIGNALS)}


def _signal_html(record: Dict[str, Any]) -> str:
    s = record.get("signal")
    return f'<span class="signal {SIGNAL_CLASS.get(s, "")}">{s}</span>' if s else "--"


def _pe_text(record: Dict[str, Any]) -> str:
    v = record.get("val")
    if not v or not isinstance(v.get("pe_pct"), (int, float)):
        return "--"
    return f'{v["pe_pct"] * 100:.0f}%'


def _pe_html(record: Dict[str, Any]) -> str:
    v = record.get("val")
    if not v or not isinstance(v.get("pe_pct"), (int, float)):
        return '<span class="neutral">--</span>'
    ref = f' <span class="pe-ref">参照{v["ref"]}</span>' if v.get("ref") else ""
    pe = f'PE {v["pe"]:.1f}' if isinstance(v.get("pe"), (int, float)) else ""
    return f'<b>{_pe_text(record)}</b> <span class="pe-sub">{pe}</span>{ref}'


def _pe_md(record: Dict[str, Any]) -> str:
    v = record.get("val")
    text = _pe_text(record)
    return f'{text}（参照{v["ref"]}）' if text != "--" and v.get("ref") else text


COL_SIGNAL = Column("信号", _signal_html, lambda r: r.get("signal") or "--")
COL_PE = Column("PE 百分位", _pe_html, _pe_md)

STOCK_COLUMNS = [COL_RANK, COL_MARKET, COL_NAME, COL_CODE, COL_PRICE, COL_CHANGE, COL_MA, COL_STATUS, COL_DEVIATION, COL_CHANGE_DATE]
COMMODITY_COLUMNS = [COL_RANK, COL_NAME, COL_CODE, COL_PRICE, COL_CHANGE, COL_MA, COL_STATUS, COL_DEVIATION, COL_CHANGE_DATE]


def _columns(base: List[Column], full: bool, pe: bool) -> List[Column]:
    """完整版在偏离度后面插入信号列（有估值的表再加 PE 百分位）。"""
    if not full:
        return base
    i = base.index(COL_DEVIATION) + 1
    return base[:i] + [COL_SIGNAL] + ([COL_PE] if pe else []) + base[i:]


class Section(NamedTuple):
    title: str
    columns: List[Column]
    records: List[Dict[str, Any]]
    note: str = ""


SIGNAL_NOTE = "信号按偏离度机械分档：≥3% 强力买入，1%~3% 买入，0~1% 观望，−1%~0 谨慎，< −1% 卖出；PE 百分位来自蛋卷基金，越低表示估值越便宜。仅供参考，不构成投资建议。"


def fmt_yield(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--"
    return f"{value:.2f}%"


# ----------------------------- HTML 渲染 ----------------------------- #

def _html_table(columns: List[Column], records: List[Dict[str, Any]]) -> str:
    head = "".join(f"<th>{c.header}</th>" for c in columns)
    body_rows = []
    for record in records:
        row_class = " class=\"changed-row\"" if record.get("changed_today") or record.get("changed_week") else ""
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


def render_html(sections: List[Section], data_date: str, generated_at: str, title_suffix: str = "",
                usd: Optional[Dict[str, Any]] = None, bonds: Optional[Dict[str, Any]] = None, footnote: str = "",
                notice: str = "") -> str:
    cards = "".join(
        f'<div class="card"><h2>{s.title}</h2>{f"<p class=note>{s.note}</p>" if s.note else ""}'
        f'<div class="table-scroll">{_html_table(s.columns, s.records)}</div></div>'
        for s in sections)
    macro_section = _macro_html(usd, bonds)
    foot = f'<div class="footnote">{footnote}</div>' if footnote else ""
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
.status-yes {{ background: #ffebee; color: #c62828; }}
.status-no {{ background: #e8f5e9; color: #2e7d32; }}
.positive {{ color: #c62828; font-weight: 600; }}
.negative {{ color: #2e7d32; font-weight: 600; }}
.neutral {{ color: #757575; }}
.change-badge {{ display: inline-block; margin-left: 8px; padding: 2px 8px; background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); color: #fff; font-size: 12px; border-radius: 10px; font-weight: 700; }}
.change-badge.week {{ background: linear-gradient(135deg, #ffb74d 0%, #ff9800 100%); }}
.stale-badge {{ display: inline-block; margin-left: 8px; padding: 2px 8px; background: #eceff1; color: #78909c; font-size: 12px; border-radius: 10px; }}
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
.usd-change.positive {{ color: #c62828; background: #ffebee; }}
.usd-change.negative {{ color: #2e7d32; background: #e8f5e9; }}
.usd-change.positive::before {{ content: "▲ "; }}
.usd-change.negative::before {{ content: "▼ "; }}
.usd-cap {{ font-size: 12px; color: #9a96b0; }}
.notice {{ margin-top: 16px; padding: 12px 18px; border-radius: 12px; background: #fff8e1; color: #8a5a00; font-size: 14px; }}
.card .note {{ margin: -6px 0 6px; font-size: 13px; color: #888; }}
.signal {{ padding: 3px 10px; border-radius: 20px; font-size: 13px; font-weight: 600; }}
.sig0 {{ background: #c62828; color: #fff; }}
.sig1 {{ background: #ffebee; color: #c62828; }}
.sig2 {{ background: #fff8e1; color: #b26a00; }}
.sig3 {{ background: #e8f5e9; color: #2e7d32; }}
.sig4 {{ background: #2e7d32; color: #fff; }}
.pe-sub, .pe-ref {{ font-size: 12px; color: #999; }}
.footnote {{ margin-top: 18px; font-size: 13px; color: #777; line-height: 1.7; }}
.footer {{ margin-top: 22px; text-align: center; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <div class="page-header">
    <h1>{title}</h1>
    <div class="meta">数据日期：{data_date} &nbsp;·&nbsp; 生成时间：{generated_at} &nbsp;·&nbsp; 排序：按偏离度由强到弱</div>
  </div>
  {notice}
  {cards}
  {macro_section}
  {foot}
  <div class="footer">数据来源：{SOURCES} · 鱼盆信号按 20 日均线计算 · 本汇总仅供参考，不构成投资建议</div>
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


def render_markdown(sections: List[Section], data_date: str, generated_at: str, title_suffix: str = "",
                    usd: Optional[Dict[str, Any]] = None, bonds: Optional[Dict[str, Any]] = None,
                    notice: str = "", extra: str = "", footnote: str = "") -> str:
    tables = "".join(f"## {s.title}\n\n{f'> {s.note}' + chr(10) + chr(10) if s.note else ''}{_md_table(s.columns, s.records)}\n\n"
                     for s in sections)
    return (
        f"# 🌍 全球行情复盘汇总{title_suffix}\n\n"
        f"> 数据日期：{data_date} · 生成时间：{generated_at} · 排序：按偏离度由强到弱\n\n"
        f"{notice}"
        f"{tables}"
        f"{_macro_md(usd, bonds)}"
        f"{extra}"
        f"{footnote + chr(10) + chr(10) if footnote else ''}"
        "---\n\n"
        f"数据来源：{SOURCES} · 鱼盆信号由本模块按 20 日均线计算 · 本汇总仅供参考，不构成投资建议\n"
    )


# ----------------------------- 从分析结果组装 ----------------------------- #

def _pct(v, d=2):
    return f"{v * 100:+.{d}f}%" if isinstance(v, (int, float)) else "--"


def _record(r: Dict[str, Any]) -> Dict[str, Any]:
    return dict(
        name=r["name"], code=r["code"], region=r["region"], flag=r["flag"], price=r.get("price"), change=r.get("chg"),
        ma20=r.get("ma"), status=r.get("status"), deviation=r.get("dev"),
        deviation_str=f"{r['dev'] * 100:.2f}%" if isinstance(r.get("dev"), (int, float)) else "N/A",
        status_change_date=r.get("since"), changed_today=r.get("changed_today"), changed_week=r.get("changed_week"),
        stale=r.get("stale"), status_date=r.get("date"), signal=r.get("signal"), val=r.get("val"),
    )


def _ranked(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = sorted((_record(r) for r in rows), key=lambda x: x["deviation"] if isinstance(x["deviation"], (int, float)) else float("-inf"),
                 reverse=True)
    for i, x in enumerate(out, 1):
        x["rank"] = i
    return out


def pick(version: str, asof: Optional[str] = None):
    """按版本筛选：返回 (分析结果, 选中的行)。"""
    data = analytics.rows(asof)
    if not data:
        return None, []
    codes = set(analytics.simple_codes()) if version == "simple" else set(INST)
    return data, [r for r in data["rows"] if r["code"] in codes and not r.get("nodata")]


def _macro_parts(asof):
    m = analytics.macro(asof)
    if not m:
        return None, None, m
    usd = None
    if m.get("dxy"):
        usd = dict(price=m["dxy"]["price"], change=m["dxy"]["chg"])
    bonds = dict(rows=[dict(term=b["term"], cn=b.get("cn"), us=b.get("us")) for b in m["bonds"]]) if m.get("bonds") else None
    return usd, bonds, m


def _notice(sel: List[Dict[str, Any]], missing: List[str]) -> List[str]:
    stale = [f"{r['name']}（{r['date']}）" for r in sel if r.get("stale")]
    lines = []
    if stale:
        lines.append(f"⚠️ 以下标的数据没有更新到最新，可能是休市或取数失败：{'、'.join(stale)}")
    if missing:
        lines.append(f"⚠️ 本次刷新失败：{'、'.join(missing)}；表中为数据库里的旧数据，没有旧数据的标的不显示")
    return lines


def _bp(v):
    return f"{v:+.0f}bp" if isinstance(v, (int, float)) else "--"


def _weekly_md(sel: List[Dict[str, Any]], data: Dict[str, Any], m: Dict[str, Any]) -> str:
    order = {c: i for i, c in enumerate(INST)}
    sel = sorted(sel, key=lambda r: order[r["code"]])
    out = [f"## 📅 本周变化（{data['week_start']} ~ {data['date']}）\n",
           "> 本周涨跌 = 本周最后一个交易日收盘 ÷ 上周最后一个交易日收盘 − 1，与上面表格里的当日涨跌不同。\n",
           "| 市场 | 名称 | 本周涨跌 | 近1月 | 上周末 → 本周状态 | 上周末 → 本周偏离度 | 当前状态持续 |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    st = {"YES": "✅", "NO": "❌", None: "--"}
    for r in sel:
        wk = "本周休市" if r.get("idle_week") else _pct(r.get("wtd"))
        flip = " 🔄" if r.get("changed_week") else ""
        out.append(f"| {r['region']} | {r['name']} | {wk} | {_pct(r.get('m1'))} | {st[r.get('prev_status')]} → {st[r.get('status')]}{flip} | "
                   f"{_pct(r.get('prev_dev'))} → {_pct(r.get('dev'))} | {r.get('days')} 个交易日（自 {r.get('since')}） |")
    up = [r["name"] for r in sel if r.get("changed_week") and r["status"] == "YES"]
    down = [r["name"] for r in sel if r.get("changed_week") and r["status"] == "NO"]
    whip = [r["name"] for r in sel if len(r.get("week_flips") or []) >= 2]
    out.append("")
    out.append(f"- 本周转为 YES：{'、'.join(up) or '无'}")
    out.append(f"- 本周转为 NO：{'、'.join(down) or '无'}")
    if whip:
        out.append(f"- 本周来回切换（临界值附近反复）：{'、'.join(whip)}")
    if m and m.get("dxy"):
        x = m["dxy"]
        out.append(f"- 美元指数：{x['price']:.2f}，本周 {_pct(x.get('wtd'))}，近1月 {_pct(x.get('m1'))}，"
                   f"{'高于' if x['status'] == 'YES' else '低于'} 20 日均线 {x['ma']:.2f}")
    if m and m.get("bonds"):
        parts = []
        for b in m["bonds"]:
            if b["term"] in ("2年", "10年", "30年"):
                parts.append(f"{b['term']} 中国 {b.get('cn', 0):.2f}%（本周 {_bp(b.get('cn_wtd'))}）/ 美国 {b.get('us', 0):.2f}%（本周 {_bp(b.get('us_wtd'))}）")
        out.append("- 国债收益率：" + "；".join(parts))
        ten = next((b for b in m["bonds"] if b["term"] == "10年"), None)
        if ten and ten.get("spread") is not None:
            out.append(f"- 中美 10 年期利差 {ten['spread']:+.0f}bp；美国 10年−2年 {_bp(m.get('us_curve'))}，中国 10年−2年 {_bp(m.get('cn_curve'))}")
    out.append("")
    return "\n".join(out) + "\n"


def build(version: str = "simple", fmt: str = "md", asof: Optional[str] = None, missing: Optional[List[str]] = None) -> Optional[str]:
    data, sel = pick(version, asof)
    if not data:
        return None
    full = version == "full"
    sections = [
        Section("📊 全球股市", _columns(STOCK_COLUMNS, full, True), _ranked([r for r in sel if r["kind"] == "stock"])),
        Section("🏅 大宗商品", _columns(COMMODITY_COLUMNS, full, False), _ranked([r for r in sel if r["kind"] == "commodity"])),
    ]
    watch = _ranked([r for r in sel if r["kind"] == "watch"])
    if watch:
        sections.append(Section("🎯 行业与个股", _columns(COMMODITY_COLUMNS, full, True), watch,
                                "单独排名，不计入上面的统计；个股按前复权价格计算。"))
    usd, bonds, m = _macro_parts(asof)
    suffix = "（精简版）" if version == "simple" else ""
    if asof:
        suffix += f" · 回看 {data['date']}"
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notice = _notice(sel, missing or [])
    foot = SIGNAL_NOTE if full else ""
    if fmt == "html":
        return render_html(sections, data["date"], generated, suffix, usd, bonds, footnote=foot,
                           notice="".join(f'<div class="notice">{x}</div>' for x in _notice([], missing or [])))
    return render_markdown(sections, data["date"], generated, suffix, usd, bonds,
                           notice="".join(f"> {x}\n" for x in notice) + ("\n" if notice else ""),
                           extra=_weekly_md(sel, data, m), footnote=foot)


def write_outputs(missing: Optional[List[str]] = None) -> List[str]:
    """刷新后写 outputs/latest_review(_simple).md/html，AI 周报流程读取这些文件。"""
    os.makedirs(OUTPUTS, exist_ok=True)
    written = []
    for version, stem in (("full", "latest_review"), ("simple", "latest_review_simple")):
        for fmt in ("md", "html"):
            text = build(version, fmt, missing=missing)
            if text is None:
                continue
            path = os.path.join(OUTPUTS, f"{stem}.{fmt}")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            written.append(path)
    return written

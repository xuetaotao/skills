"""
增强版报告生成Agent
生成美观的HTML可视化报告
"""

from typing import Dict, Any, List
from datetime import datetime
import json

from .base import BaseAgent
from config import REPORT_CONFIG


class ReportAgent(BaseAgent):
    def __init__(self):
        super().__init__("ReportAgent")

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.log_info("开始生成报告...")

        analyzed_data = context.get("analyzed_data", {})
        signals = context.get("signals", {})
        ranked_signals = context.get("ranked_signals", [])
        summary = context.get("summary", {})

        json_report = self._generate_json_report(analyzed_data, signals, ranked_signals, summary)
        markdown_report = self._generate_markdown_report(analyzed_data, signals, ranked_signals, summary)
        html_report = self._generate_html_report(analyzed_data, signals, ranked_signals, summary)

        result = {
            "status": "success",
            "json_report": json_report,
            "markdown_report": markdown_report,
            "html_report": html_report,
            "timestamp": datetime.now().isoformat()
        }

        self.log_info("报告生成完成")
        return result

    def _generate_json_report(self, analyzed_data: Dict, signals: Dict, ranked_signals: List, summary: Dict) -> str:
        report = {
            "报告时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "鱼盆模型分析": "V1.0",
            "市场概览": summary,
            "各指数详情": [],
            "交易信号": ranked_signals
        }

        for name, signal in signals.items():
            detail = {
                "指数名称": name,
                "代码": analyzed_data.get(name, {}).get("code", ""),
                "当前价格": analyzed_data.get(name, {}).get("当前价格", 0),
                "MA20": analyzed_data.get(name, {}).get("MA20", 0),
                "偏离度": analyzed_data.get(name, {}).get("偏离度百分比", "0.00%"),
                "状态": signal.get("状态", "NO"),
                "交易信号": signal.get("当前信号", ""),
                "操作建议": signal.get("操作建议", ""),
                "详细建议": signal.get("详细建议", "")
            }
            report["各指数详情"].append(detail)

        return json.dumps(report, ensure_ascii=False, indent=2)

    def _generate_markdown_report(self, analyzed_data: Dict, signals: Dict, ranked_signals: List, summary: Dict) -> str:
        lines = []

        lines.append("# 🐟 鱼盆模型量化分析报告")
        lines.append("")
        lines.append(f"**报告时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("---\n")

        lines.append("## 📊 市场概览")
        lines.append("")
        lines.append(f"- **整体趋势**: {summary.get('整体趋势', '未知')}")
        lines.append(f"- **市场情绪**: {summary.get('市场情绪', '未知')}")
        lines.append(f"- **YES指数数量**: {summary.get('YES数量', 0)}")
        lines.append(f"- **NO指数数量**: {summary.get('NO数量', 0)}")
        lines.append(f"- **平均偏离度**: {summary.get('平均偏离度', '0.00%')}")
        lines.append(f"- **最强指数**: {summary.get('最强指数', '无')} ({summary.get('最强偏离度', '0.00%')})")
        lines.append("")

        lines.append("---\n")
        lines.append("## 📈 趋势强度排名")
        lines.append("")

        if ranked_signals:
            lines.append("| 排名 | 指数名称 | 状态 | 偏离度 | 操作建议 |")
            lines.append("|------|----------|------|--------|----------|")
            for item in ranked_signals:
                偏离度 = item['偏离度']
                偏离度_str = f"{偏离度*100:.2f}%" if 偏离度 != -999 else "N/A"
                lines.append(f"| {item['趋势强度排名']} | {item['指数名称']} | {item['状态'] or '数据获取失败'} | {偏离度_str} | {item['操作建议']} |")
        lines.append("")

        lines.append("---\n")
        lines.append("## 🔍 各指数详细分析")
        lines.append("")

        for name, signal in signals.items():
            analysis = analyzed_data.get(name, {})
            数据状态 = analysis.get('数据状态', '成功')

            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"- **代码**: {analysis.get('code', 'N/A')}")

            if 数据状态 == '获取失败':
                lines.append(f"- **状态**: ❌ 数据获取失败")
                lines.append(f"- **交易信号**: 无法生成")
                lines.append(f"- **操作建议**: 待数据修复")
            else:
                lines.append(f"- **当前价格**: {analysis.get('当前价格', 0) or 0:.2f}")
                lines.append(f"- **MA20**: {analysis.get('MA20', 0) or 0:.2f}")
                lines.append(f"- **偏离度**: {analysis.get('偏离度百分比', '0.00%')}")
                lines.append(f"- **状态**: {signal.get('状态', 'NO')}")
                lines.append(f"- **交易信号**: {signal.get('当前信号', '')}")
                lines.append(f"- **操作建议**: {signal.get('详细建议', '')}")
            lines.append("")

        lines.append("---\n")
        lines.append("## ⚠️ 风险提示")
        lines.append("")
        lines.append("1. 鱼盆模型适用于趋势市，震荡市中可能出现频繁假信号")
        lines.append("2. 模型胜率约20-30%，靠的是赚大赔小的策略")
        lines.append("3. 本报告仅供参考，不构成投资建议")
        lines.append("4. 请结合自身风险承受能力做出投资决策")
        lines.append("")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    def _generate_html_report(self, analyzed_data: Dict, signals: Dict, ranked_signals: List, summary: Dict) -> str:
        html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>鱼盆模型分析报告 - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .header {{
            text-align: center;
            padding: 40px 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 20px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
        }}

        .header h1 {{
            color: white;
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}

        .header .subtitle {{
            color: rgba(255,255,255,0.9);
            font-size: 1.2em;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
        }}

        .header .data-info {{
            color: #ffd700;
            font-weight: bold;
        }}

        .header .separator {{
            color: rgba(255,255,255,0.5);
        }}

        .header .refresh-info {{
            color: rgba(255,255,255,0.8);
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: white;
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
        }}

        .stat-card .label {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 10px;
        }}

        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #2c3e50;
        }}

        .stat-card .trend {{
            font-size: 0.9em;
            margin-top: 10px;
            padding: 5px 15px;
            border-radius: 20px;
            display: inline-block;
        }}

        .trend.up {{
            background: #e8f5e9;
            color: #2e7d32;
        }}

        .trend.down {{
            background: #ffebee;
            color: #c62828;
        }}

        .trend.neutral {{
            background: #fff3e0;
            color: #ef6c00;
        }}

        .section {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }}

        .section-title {{
            font-size: 1.8em;
            color: #2c3e50;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 3px solid #667eea;
        }}

        .index-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .index-table thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}

        .index-table th {{
            color: white;
            padding: 15px 10px;
            text-align: left;
            font-weight: 600;
        }}

        .index-table td {{
            padding: 15px 10px;
            border-bottom: 1px solid #eee;
        }}

        .index-table tbody tr {{
            transition: background 0.2s;
        }}

        .index-table tbody tr:hover {{
            background: #f8f9fa;
        }}

        .index-table tbody tr:last-child td {{
            border-bottom: none;
        }}

        .status-yes {{
            background: #e8f5e9;
            color: #2e7d32;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            display: inline-block;
            min-width: 60px;
            text-align: center;
        }}

        .status-no {{
            background: #ffebee;
            color: #c62828;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            display: inline-block;
            min-width: 60px;
            text-align: center;
        }}

        .deviation {{
            font-weight: 600;
            padding: 5px 10px;
            border-radius: 5px;
        }}

        .deviation.positive {{
            background: #e8f5e9;
            color: #2e7d32;
        }}

        .deviation.negative {{
            background: #ffebee;
            color: #c62828;
        }}

        .deviation.neutral {{
            background: #fff3e0;
            color: #ef6c00;
        }}

        .rank-badge {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
        }}

        .rank-1 {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}

        .rank-2 {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }}

        .rank-3 {{
            background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
        }}

        .action-buy {{
            background: #e8f5e9;
            color: #2e7d32;
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: 600;
            display: inline-block;
        }}

        .action-sell {{
            background: #ffebee;
            color: #c62828;
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: 600;
            display: inline-block;
        }}

        .action-hold {{
            background: #fff3e0;
            color: #ef6c00;
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: 600;
            display: inline-block;
        }}

        .source-tag {{
            background: #e3f2fd;
            color: #1565c0;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }}

        .date-tag {{
            background: #f3e5f5;
            color: #7b1fa2;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 500;
        }}

        .data-failed-row {{
            background: #ffebee !important;
            opacity: 0.7;
        }}

        .data-error {{
            background: #ffcdd2;
            color: #c62828;
            padding: 5px 15px;
            border-radius: 5px;
            font-weight: bold;
        }}

        .signal-tag {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: 600;
            margin: 5px;
        }}

        .signal-strong-buy {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
        }}

        .signal-buy {{
            background: linear-gradient(135deg, #56ab2f 0%, #a8e063 100%);
            color: white;
        }}

        .signal-watch {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
        }}

        .signal-cautious {{
            background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
            color: white;
        }}

        .signal-sell {{
            background: linear-gradient(135deg, #c31432 0%, #240b36 100%);
            color: white;
        }}

        .detail-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}

        .detail-card {{
            background: #f8f9fa;
            border-radius: 10px;
            padding: 20px;
            border-left: 4px solid #667eea;
        }}

        .detail-card h4 {{
            color: #2c3e50;
            margin-bottom: 15px;
            font-size: 1.2em;
        }}

        .detail-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e0e0e0;
        }}

        .detail-item:last-child {{
            border-bottom: none;
        }}

        .detail-item .label {{
            color: #666;
        }}

        .detail-item .value {{
            font-weight: 600;
            color: #2c3e50;
        }}

        .footer {{
            text-align: center;
            padding: 30px;
            color: rgba(255,255,255,0.7);
            font-size: 0.9em;
        }}

        .warning {{
            background: linear-gradient(135deg, #ff6b6b 0%, #ffc107 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
        }}

        .warning h4 {{
            margin-bottom: 10px;
        }}

        .warning ul {{
            list-style: none;
            padding-left: 0;
        }}

        .warning li {{
            padding: 5px 0;
        }}

        .highlight-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}

        .highlight-box h3 {{
            margin-bottom: 10px;
        }}

        .yes-count {{
            color: #4caf50;
            font-weight: bold;
            text-shadow: 0 0 10px rgba(76, 175, 80, 0.5);
        }}

        .no-count {{
            color: #ff8a80;
            font-weight: bold;
            text-shadow: 0 0 10px rgba(255, 138, 128, 0.5);
        }}

        .status-changed-row {{
            background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%) !important;
            animation: pulse-highlight 2s ease-in-out infinite;
        }}

        @keyframes pulse-highlight {{
            0%, 100% {{ box-shadow: inset 0 0 0 2px #ff9800; }}
            50% {{ box-shadow: inset 0 0 0 4px #ff9800; }}
        }}

        .status-change-badge {{
            display: inline-block;
            margin-left: 8px;
            padding: 2px 8px;
            background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%);
            color: white;
            font-size: 0.75em;
            border-radius: 10px;
            font-weight: bold;
            animation: badge-blink 1.5s ease-in-out infinite;
        }}

        @keyframes badge-blink {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
        }}

        .pe-low {{
            color: #2e7d32;
            font-weight: bold;
        }}

        .pe-high {{
            color: #c62828;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🐟 鱼盆模型量化分析报告</h1>
            <div class="subtitle">
                <span class="data-info">📅 数据日期: {summary.get('数据日期', datetime.now().strftime('%Y-%m-%d'))}</span>
                <span class="separator">|</span>
                <span class="refresh-info">🕐 刷新时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}</span>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">整体趋势</div>
                <div class="value">{summary.get('整体趋势', '未知')}</div>
                <div class="trend {'up' if '强势' in summary.get('整体趋势', '') or '偏强' in summary.get('整体趋势', '') else 'down' if '弱' in summary.get('整体趋势', '') else 'neutral'}">
                    {summary.get('市场情绪', '未知')}
                </div>
            </div>
            <div class="stat-card">
                <div class="label">YES 指数</div>
                <div class="value yes-count">{summary.get('YES数量', 0)}</div>
                <div class="trend up">线上持有</div>
            </div>
            <div class="stat-card">
                <div class="label">NO 指数</div>
                <div class="value no-count">{summary.get('NO数量', 0)}</div>
                <div class="trend down">线下观望</div>
            </div>
            <div class="stat-card">
                <div class="label">最强指数</div>
                <div class="value" style="font-size: 1.5em;">{summary.get('最强指数', '无')}</div>
                <div class="trend up">{summary.get('最强偏离度', '0.00%')}</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">📈 趋势强度排名</h2>
            <table class="index-table">
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>指数名称</th>
                        <th>代码</th>
                        <th>现价</th>
                        <th>临界值(MA20)</th>
                        <th>状态</th>
                        <th>偏离度</th>
                        {f'<th>PE百分位</th>' if REPORT_CONFIG.get('显示PE百分位', True) else ''}
                        <th>状态转变时间</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_table_rows(ranked_signals, signals, analyzed_data, summary)}
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2 class="section-title">💡 操作建议</h2>
            <div class="highlight-box">
                <h3>市场综合分析</h3>
                <p>当前市场 <span class="yes-count">{summary.get('YES数量', 0)}</span> 个指数在20日线上，
                   <span class="no-count">{summary.get('NO数量', 0)}</span> 个指数在20日线下。</p>
                <p style="margin-top: 10px;">平均偏离度：<strong>{summary.get('平均偏离度', '0.00%')}</strong></p>
            </div>
            {self._generate_brief_interpretation_html(summary)}
            <h3 style="margin: 20px 0 15px 0;">强势指数（可关注）</h3>
            {self._generate_signal_list(ranked_signals, 'YES', signals)}

            <h3 style="margin: 20px 0 15px 0;">弱势指数（需谨慎）</h3>
            {self._generate_signal_list(ranked_signals, 'NO', signals)}
        </div>

        <div class="section">
            <h2 class="section-title">🔍 各指数详细数据</h2>
            <div class="detail-grid">
                {self._generate_detail_cards(signals, analyzed_data)}
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">⚠️ 风险提示</h2>
            <div class="warning">
                <h4>⚠️ 重要提醒</h4>
                <ul>
                    <li>• 鱼盆模型适用于趋势市，震荡行情中可能出现频繁假信号</li>
                    <li>• 模型胜率约20-30%，靠的是赚大赔小的策略</li>
                    <li>• 本报告仅供参考，不构成投资建议</li>
                    <li>• 请结合自身风险承受能力做出投资决策</li>
                    <li>• 投资有风险，入市需谨慎</li>
                </ul>
            </div>
        </div>

        <div class="footer">
            <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>鱼盆模型量化分析系统 | 基于20日均线趋势跟踪策略</p>
        </div>
    </div>
</body>
</html>"""

        return html_template

    def _generate_table_rows(self, ranked_signals: List, signals: Dict, analyzed_data: Dict, summary: Dict) -> str:
        rows = []
        数据日期 = summary.get('数据日期', datetime.now().strftime('%Y-%m-%d'))
        for item in ranked_signals:
            name = item['指数名称']
            signal = signals.get(name, {})
            analysis = analyzed_data.get(name, {})

            数据状态 = analysis.get('数据状态', '成功')

            if 数据状态 == '获取失败':
                rank_class = f'rank-badge rank-{item["趋势强度排名"]}' if item["趋势强度排名"] <= 3 else 'rank-badge'
                rows.append(f"""
                <tr class="data-failed-row">
                    <td><span class="{rank_class}">{item['趋势强度排名']}</span></td>
                    <td><strong>{name}</strong></td>
                    <td><code>{analysis.get('code', 'N/A')}</code></td>
                    <td colspan="6"><span class="data-error">❌ 数据获取失败</span></td>
                </tr>
            """)
                continue

            偏离度 = item['偏离度']
            if 偏离度 == -999:
                deviation_str = "N/A"
                deviation_class = "neutral"
            else:
                deviation_class = 'positive' if 偏离度 > 0 else 'negative' if 偏离度 < 0 else 'neutral'
                deviation_str = f"{偏离度*100:+.2f}%"

            if item['状态'] is None:
                status_class = 'status-error'
                status_text = '❌ 数据获取失败'
            else:
                status_class = 'status-yes' if item['状态'] == 'YES' else 'status-no'
                status_text = '✅ YES' if item['状态'] == 'YES' else '❌ NO'

            rank_class = f'rank-badge rank-{item["趋势强度排名"]}' if item["趋势强度排名"] <= 3 else 'rank-badge'

            操作 = signal.get('操作建议', '')
            if '买入' in 操作 or '持有' in 操作:
                action_class = 'action-buy'
                action_text = '✅ 买入/持有'
            elif '观望' in 操作:
                action_class = 'action-hold'
                action_text = '⏳ 观望'
            else:
                action_class = 'action-sell'
                action_text = '🚫 卖出'

            现价 = analysis.get('当前价格', 0) or 0
            MA20 = analysis.get('MA20', 0) or 0
            代码 = analysis.get('code', 'N/A')
            状态转变时间 = analysis.get('状态开始日期', '') or ''
            
            show_pe = REPORT_CONFIG.get('显示PE百分位', True)
            if show_pe:
                PE百分位 = analysis.get('PE百分位')
                if PE百分位 is not None:
                    if PE百分位 < 30:
                        pe_class = 'pe-low'
                        pe_str = f'<span class="{pe_class}">{PE百分位:.1f}%</span>'
                    elif PE百分位 > 70:
                        pe_class = 'pe-high'
                        pe_str = f'<span class="{pe_class}">{PE百分位:.1f}%</span>'
                    else:
                        pe_str = f'{PE百分位:.1f}%'
                else:
                    pe_str = '--'
            else:
                pe_str = ''

            if isinstance(状态转变时间, str):
                if 'T' in 状态转变时间:
                    状态转变时间 = 状态转变时间.split('T')[0]
            elif hasattr(状态转变时间, 'strftime'):
                状态转变时间 = 状态转变时间.strftime('%Y-%m-%d')

            is_status_changed_today = (状态转变时间 == 数据日期)
            row_class = 'status-changed-row' if is_status_changed_today else ''
            changed_badge = '<span class="status-change-badge">⚡ 今日转变</span>' if is_status_changed_today else ''

            pe_cell = f'<td>{pe_str}</td>' if show_pe else ''

            rows.append(f"""
                <tr class="{row_class}">
                    <td><span class="{rank_class}">{item['趋势强度排名']}</span></td>
                    <td><strong>{name}</strong>{changed_badge}</td>
                    <td><code>{代码}</code></td>
                    <td><strong>{现价:.2f}</strong></td>
                    <td>{MA20:.2f}</td>
                    <td><span class="{status_class}">{status_text}</span></td>
                    <td><span class="deviation {deviation_class}">{deviation_str}</span></td>
                    {pe_cell}
                    <td>{状态转变时间}</td>
                </tr>
            """)

        return "\n".join(rows)

    def _generate_detail_cards(self, signals: Dict, analyzed_data: Dict) -> str:
        cards = []
        for name, signal in signals.items():
            analysis = analyzed_data.get(name, {})
            数据状态 = analysis.get('数据状态', '成功')

            if 数据状态 == '获取失败':
                cards.append(f"""
                <div class="detail-card" style="border-left-color: #c62828;">
                    <h4>{name} <span class="❌">数据获取失败</span></h4>
                    <div class="detail-item">
                        <span class="label">代码</span>
                        <span class="value">{analysis.get('code', 'N/A')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">状态</span>
                        <span class="value" style="color: #c62828;">❌ 数据获取失败</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">操作建议</span>
                        <span class="value">待数据修复</span>
                    </div>
                </div>
            """)
                continue

            偏离度 = analysis.get('偏离度', 0) or 0
            deviation_class = 'positive' if 偏离度 > 0 else 'negative' if 偏离度 < 0 else 'neutral'

            cards.append(f"""
                <div class="detail-card">
                    <h4>{name} <span class="{signal.get('状态', 'NO') == 'YES' and '✅' or '❌'}">{signal.get('状态', 'NO')}</span></h4>
                    <div class="detail-item">
                        <span class="label">代码</span>
                        <span class="value">{analysis.get('code', 'N/A')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">当前价格</span>
                        <span class="value">{analysis.get('当前价格', 0) or 0:.2f}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">MA20</span>
                        <span class="value">{analysis.get('MA20', 0) or 0:.2f}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">偏离度</span>
                        <span class="value deviation {deviation_class}">{analysis.get('偏离度百分比', '0.00%')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">详细建议</span>
                        <span class="value">{signal.get('详细建议', '')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">数据源</span>
                        <span class="source-tag">{analysis.get('数据源', 'N/A')}</span>
                    </div>
                    <div class="detail-item">
                        <span class="label">数据日期</span>
                        <span class="date-tag">{analysis.get('数据日期', 'N/A')}</span>
                    </div>
                </div>
            """)

        return "\n".join(cards)

    def _generate_signal_list(self, ranked_signals: List, status_filter: str, signals: Dict) -> str:
        filtered = [s for s in ranked_signals if s['状态'] == status_filter]

        if not filtered:
            return f'<p style="color: #666;">暂无{status_filter}指数</p>'

        items = []
        for item in filtered[:3]:
            name = item['指数名称']
            signal = signals.get(name, {})
            deviation = item['偏离度'] * 100
            items.append(f"""
                <div class="signal-tag {'signal-buy' if status_filter == 'YES' else 'signal-sell'}">
                    {name} <span style="opacity:0.8">({deviation:+.2f}%)</span>
                </div>
            """)

        if len(filtered) <= 3:
            return "\n".join(items)

        hidden_items = []
        for item in filtered[3:]:
            name = item['指数名称']
            deviation = item['偏离度'] * 100
            hidden_items.append(f"""
                <div class="signal-tag {'signal-buy' if status_filter == 'YES' else 'signal-sell'}">
                    {name} <span style="opacity:0.8">({deviation:+.2f}%)</span>
                </div>
            """)

        expand_id = f"expand-{status_filter.lower()}"
        return f"""
            {"\n".join(items)}
            <div id="{expand_id}" style="display: none;">
                {"\n".join(hidden_items)}
            </div>
            <button onclick="document.getElementById('{expand_id}').style.display = document.getElementById('{expand_id}').style.display === 'none' ? 'block' : 'none'; this.textContent = document.getElementById('{expand_id}').style.display === 'none' ? '展开全部 ({len(filtered)}个)' : '收起';" 
                    style="margin-top: 10px; padding: 8px 16px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 20px; cursor: pointer; font-size: 0.9em;">
                展开全部 ({len(filtered)}个)
            </button>
        """

    def _generate_brief_interpretation_html(self, summary: Dict) -> str:
        interpretations = summary.get("简要解读", [])
        if not interpretations:
            return ""

        items = []
        for text in interpretations:
            items.append(f'<li style="margin: 8px 0; color: #444;">• {text}</li>')

        return f"""
            <div style="background: #f8f9fa; border-radius: 10px; padding: 20px; margin: 20px 0; border-left: 4px solid #667eea;">
                <h4 style="color: #2c3e50; margin-bottom: 15px;">📝 简要解读</h4>
                <ul style="list-style: none; padding: 0; margin: 0;">
                    {"".join(items)}
                </ul>
            </div>
        """
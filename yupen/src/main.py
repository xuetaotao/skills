"""
鱼盆模型量化分析系统
主程序入口
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import MultiAgentOrchestrator
from config import INDICES, REPORT_CONFIG


def main():
    print("=" * 60)
    print("🐟 鱼盆模型多Agent量化分析系统")
    print("=" * 60)
    print()

    orchestrator = MultiAgentOrchestrator()

    print("开始运行多Agent工作流...")
    print()

    result = orchestrator.run_workflow(
        indices=INDICES,
        lookback_days=60
    )

    print()
    print("=" * 60)
    print("📊 分析结果汇总")
    print("=" * 60)

    if result.get("status") == "success":
        summary = result.get("summary", {})

        print(f"整体趋势: {summary.get('整体趋势', '未知')}")
        print(f"市场情绪: {summary.get('市场情绪', '未知')}")
        print(f"YES数量: {summary.get('YES数量', 0)}")
        print(f"NO数量: {summary.get('NO数量', 0)}")
        print(f"最强指数: {summary.get('最强指数', '无')} ({summary.get('最强偏离度', '0.00%')})")
        print()

        ranked_signals = result.get("ranked_signals", [])
        if ranked_signals:
            print("趋势强度排名:")
            print("-" * 50)
            for item in ranked_signals:
                print(f"  {item['趋势强度排名']}. {item['指数名称']:10} | {item['状态']} | 偏离度: {item['偏离度']*100:.2f}% | {item['操作建议']}")
        print()

        report_result = result.get("results", {}).get("report_generator", {})
        markdown_report = report_result.get("markdown_report", "")

        output_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(output_dir, exist_ok=True)

        latest_json = os.path.join(output_dir, "latest_report.json")
        latest_md = os.path.join(output_dir, "latest_report.md")
        latest_html = os.path.join(output_dir, "latest_report.html")
        
        json_report = report_result.get("json_report", "{}")
        with open(latest_json, "w", encoding="utf-8") as f:
            f.write(json_report)
        with open(latest_md, "w", encoding="utf-8") as f:
            f.write(markdown_report)

        html_report = report_result.get("html_report", "")
        with open(latest_html, "w", encoding="utf-8") as f:
            f.write(html_report)

        print(f"📁 报告已保存:")
        print(f"   JSON: {latest_json}")
        print(f"   Markdown: {latest_md}")
        print(f"   HTML: {latest_html}")
        print()

        print(f"执行耗时: {result.get('execution_time', 0):.2f} 秒")

    else:
        print(f"❌ 执行失败: {result.get('message', '未知错误')}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
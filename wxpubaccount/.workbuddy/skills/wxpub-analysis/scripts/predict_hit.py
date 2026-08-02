# -*- coding: utf-8 -*-
"""爆款预测器：基于历史数据规律，判断"想写的文章"是否能成爆款。

用法：
  python predict_hit.py --title "标题草稿" --topics "微信,AI,工具" [--day 周二]
  python predict_hit.py                    # 交互式输入

输出：评分卡（阅读爆款潜力 / 涨粉潜力 / 综合建议 / 历史相似案例）

评分依据 hit_baseline.json（由 update_baseline.py 生成，每次数据复盘后自动更新）。
"""
import argparse
import os
import sys

from prediction_core import (
    find_workspace_root,
    load_baseline,
    render_prediction_card,
    score_topic_idea,
    split_topics,
)


def configure_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    configure_stdout()
    root = find_workspace_root(os.path.dirname(os.path.abspath(__file__)))

    ap = argparse.ArgumentParser(description="爆款预测器")
    ap.add_argument("workspace", nargs="?", help="工作空间目录，可省略")
    ap.add_argument("--title", help="标题草稿")
    ap.add_argument("--topics", help="主题关键词，逗号分隔，如 '微信,AI,工具'")
    ap.add_argument("--day", default="周二", help="计划发文星期（周一~周日），默认周二")
    args = ap.parse_args()

    base = args.workspace or os.environ.get("WXPUB_DIR", root)

    title = args.title or input("📝 标题草稿（可粗略）: ").strip()
    topics_raw = args.topics or input("📝 主题关键词（逗号分隔，如 微信,AI,理财）: ").strip()
    topics = split_topics(topics_raw)

    if not title or not topics:
        print("❌ 标题和主题关键词都不能为空")
        return 1

    try:
        baseline = load_baseline(base)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1

    result = score_topic_idea(title=title, topics=topics, day=args.day, baseline=baseline)
    print(render_prediction_card(result, baseline))
    return 0


if __name__ == "__main__":
    sys.exit(main())

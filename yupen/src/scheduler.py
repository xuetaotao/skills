"""
定时任务调度器
按配置时间在交易日自动运行鱼盆模型分析
"""

import schedule
import time
import logging
from datetime import datetime
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import MultiAgentOrchestrator
from config import INDICES, REPORT_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class YupenScheduler:
    def __init__(self):
        self.orchestrator = MultiAgentOrchestrator()
        self.is_running = False

    def run_analysis(self):
        logger.info("=" * 60)
        logger.info(f"🕐 定时任务触发 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        try:
            result = self.orchestrator.run_workflow(
                indices=INDICES,
                lookback_days=60
            )

            if result.get("status") == "success":
                summary = result.get("summary", {})
                logger.info(f"✅ 分析完成")
                logger.info(f"   整体趋势: {summary.get('整体趋势', '未知')}")
                logger.info(f"   市场情绪: {summary.get('市场情绪', '未知')}")
                logger.info(f"   YES数量: {summary.get('YES数量', 0)}, NO数量: {summary.get('NO数量', 0)}")
                logger.info(f"   最强指数: {summary.get('最强指数', '无')} ({summary.get('最强偏离度', '0.00%')})")
            else:
                logger.error(f"❌ 分析失败: {result.get('message', '未知错误')}")

            return result

        except Exception as e:
            logger.error(f"❌ 定时任务执行失败: {str(e)}")
            raise

    def start(self):
        run_time = REPORT_CONFIG.get("交易时间", "19:00")
        schedule.every().monday.at(run_time).do(self._scheduled_run)
        schedule.every().tuesday.at(run_time).do(self._scheduled_run)
        schedule.every().wednesday.at(run_time).do(self._scheduled_run)
        schedule.every().thursday.at(run_time).do(self._scheduled_run)
        schedule.every().friday.at(run_time).do(self._scheduled_run)

        self.is_running = True
        logger.info("⏰ 定时调度器已启动")
        logger.info(f"📅 将在每个交易日的 {run_time} 自动运行分析")
        logger.info("按 Ctrl+C 停止调度器")

        self._run_loop()

    def _scheduled_run(self):
        try:
            self.run_analysis()
        except Exception as e:
            logger.error(f"定时任务执行异常: {str(e)}")

    def _run_loop(self):
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)

    def stop(self):
        self.is_running = False
        logger.info("定时调度器已停止")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='鱼盆模型定时调度器')
    parser.add_argument('--once', action='store_true', help='立即运行一次（不启动调度器）')
    parser.add_argument('--test', action='store_true', help='测试模式（使用模拟数据）')

    args = parser.parse_args()

    if args.once:
        scheduler = YupenScheduler()
        scheduler.run_analysis()
    else:
        scheduler = YupenScheduler()
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("收到停止信号")
            scheduler.stop()


if __name__ == "__main__":
    main()

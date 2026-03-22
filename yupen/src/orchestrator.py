"""
多Agent协调器
负责协调各个Agent的工作，实现多Agent协作
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from agents import (
    DataCollectorAgent,
    DataAnalyzerAgent,
    SignalGeneratorAgent,
    ReportAgent
)

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    def __init__(self):
        self.agents = {
            "collector": DataCollectorAgent(),
            "analyzer": DataAnalyzerAgent(),
            "signal_generator": SignalGeneratorAgent(),
            "report_generator": ReportAgent()
        }

        self.context: Dict[str, Any] = {}
        self.execution_log: List[Dict[str, Any]] = []

        logger.info("MultiAgentOrchestrator 初始化完成")
        logger.info(f"已注册Agent: {list(self.agents.keys())}")

    def run_workflow(self, indices: List[Dict[str, str]], lookback_days: int = 60) -> Dict[str, Any]:
        self.context = {
            "indices": indices,
            "lookback_days": lookback_days,
            "ma_period": 20,
            "start_time": datetime.now()
        }

        logger.info("=" * 60)
        logger.info("开始执行多Agent工作流")
        logger.info("=" * 60)

        self._log_execution("WORKFLOW_START", "工作流开始执行")

        collector_result = self._execute_agent("collector")
        if collector_result.get("status") not in ["success", "partial_success"]:
            return self._error_response("数据采集失败", collector_result)

        self.context["raw_data"] = collector_result.get("data", {})

        analyzer_result = self._execute_agent("analyzer")
        if analyzer_result.get("status") != "success":
            return self._error_response("数据分析失败", analyzer_result)

        self.context["analyzed_data"] = analyzer_result.get("analyzed_data", {})

        signal_result = self._execute_agent("signal_generator")
        if signal_result.get("status") != "success":
            return self._error_response("信号生成失败", signal_result)

        self.context["signals"] = signal_result.get("signals", {})
        self.context["ranked_signals"] = signal_result.get("ranked_signals", [])
        self.context["summary"] = signal_result.get("summary", {})

        report_result = self._execute_agent("report_generator")

        self.context["report"] = report_result

        self._log_execution("WORKFLOW_COMPLETE", "工作流执行完成")

        logger.info("=" * 60)
        logger.info("多Agent工作流执行完成")
        logger.info("=" * 60)

        return {
            "status": "success",
            "workflow": "鱼盆模型多Agent分析",
            "execution_time": (datetime.now() - self.context["start_time"]).total_seconds(),
            "results": {
                "collector": collector_result,
                "analyzer": analyzer_result,
                "signal_generator": signal_result,
                "report_generator": report_result
            },
            "summary": signal_result.get("summary", {}),
            "ranked_signals": signal_result.get("ranked_signals", [])
        }

    def _execute_agent(self, agent_name: str) -> Dict[str, Any]:
        agent = self.agents.get(agent_name)
        if not agent:
            logger.error(f"Agent {agent_name} 不存在")
            return {"status": "error", "message": f"Agent {agent_name} 不存在"}

        logger.info(f"[{agent_name}] 开始执行...")

        start_time = datetime.now()
        try:
            result = agent.execute(self.context)
            execution_time = (datetime.now() - start_time).total_seconds()

            self._log_execution(agent_name, "success", execution_time)

            logger.info(f"[{agent_name}] 执行完成，耗时: {execution_time:.2f}秒")

            return result

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Agent {agent_name} 执行失败: {str(e)}"

            self._log_execution(agent_name, "error", execution_time, str(e))

            logger.error(error_msg)
            return {"status": "error", "message": error_msg}

    def _log_execution(self, agent_name: str, status: str, 
                       execution_time: float = 0, error: str = "") -> None:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "status": status,
            "execution_time": execution_time
        }
        if error:
            log_entry["error"] = error

        self.execution_log.append(log_entry)

    def _error_response(self, message: str, details: Dict) -> Dict[str, Any]:
        return {
            "status": "error",
            "message": message,
            "details": details,
            "execution_log": self.execution_log
        }

    def get_agent_status(self) -> Dict[str, str]:
        return {
            name: "ready" for name in self.agents.keys()
        }

    def get_execution_log(self) -> List[Dict[str, Any]]:
        return self.execution_log.copy()

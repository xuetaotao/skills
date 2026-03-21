"""
Agent基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self._state: Dict[str, Any] = {}

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def update_state(self, key: str, value: Any) -> None:
        self._state[key] = value
        self.logger.debug(f"状态更新 {key}: {value}")

    def get_state(self, key: str) -> Optional[Any]:
        return self._state.get(key)

    def clear_state(self) -> None:
        self._state.clear()

    def log_info(self, message: str) -> None:
        self.logger.info(f"[{self.name}] {message}")

    def log_error(self, message: str) -> None:
        self.logger.error(f"[{self.name}] {message}")

    def log_warning(self, message: str) -> None:
        self.logger.warning(f"[{self.name}] {message}")
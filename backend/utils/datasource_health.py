"""
数据源健康检查 & 自动降级管理

功能：
- 数据源可用性探测
- 连续失败计数 & 自动禁用
- 多数据源优先级降级链
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 连续失败阈值：超过此值自动禁用该数据源
DEFAULT_FAILURE_THRESHOLD = 5
# 禁用冷却时间（秒）：超过此时间后重新尝试
DEFAULT_COOLDOWN_SECONDS = 600  # 10 分钟


@dataclass
class DataSourceStatus:
    """数据源状态"""
    name: str
    available: bool = True
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    disabled_until: float = 0.0  # 禁用截止时间戳
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS

    def record_success(self) -> None:
        self.total_successes += 1
        self.consecutive_failures = 0
        self.last_success_time = time.time()
        self.available = True
        self.disabled_until = 0.0

    def record_failure(self, error: str = "") -> None:
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self.available = False
            self.disabled_until = time.time() + self.cooldown_seconds
            logger.warning(
                f"数据源 {self.name} 连续失败 {self.consecutive_failures} 次，"
                f"已自动禁用 {self.cooldown_seconds}s | 最后错误: {error}"
            )

    def check_and_reenable(self) -> bool:
        """检查冷却时间是否已过，自动重新启用"""
        if not self.available and self.disabled_until > 0 and time.time() >= self.disabled_until:
            self.available = True
            self.consecutive_failures = 0
            self.disabled_until = 0.0
            logger.info(f"数据源 {self.name} 冷却时间已过，已重新启用")
            return True
        return False

    def is_available(self) -> bool:
        self.check_and_reenable()
        return self.available

    def summary(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "disabled_until": self.disabled_until if self.disabled_until > 0 else None,
        }


class DataSourceHealthManager:
    """数据源健康管理器

    管理多个数据源的可用性状态，支持自动禁用和恢复。
    """

    def __init__(self):
        self._sources: Dict[str, DataSourceStatus] = {}

    def register(self, name: str, failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
                 cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS) -> DataSourceStatus:
        """注册数据源"""
        if name not in self._sources:
            self._sources[name] = DataSourceStatus(
                name=name,
                failure_threshold=failure_threshold,
                cooldown_seconds=cooldown_seconds,
            )
        return self._sources[name]

    def get(self, name: str) -> Optional[DataSourceStatus]:
        return self._sources.get(name)

    def record_success(self, name: str) -> None:
        status = self._sources.get(name)
        if status:
            status.record_success()

    def record_failure(self, name: str, error: str = "") -> None:
        status = self._sources.get(name)
        if status:
            status.record_failure(error)

    def is_available(self, name: str) -> bool:
        status = self._sources.get(name)
        if not status:
            return True  # 未注册的数据源默认可用
        return status.is_available()

    def get_available_sources(self, priority_order: List[str]) -> List[str]:
        """按优先级顺序返回当前可用的数据源列表"""
        return [name for name in priority_order if self.is_available(name)]

    def get_next_available(self, priority_order: List[str], current: str) -> Optional[str]:
        """获取当前数据源的下一个可用备选"""
        available = self.get_available_sources(priority_order)
        try:
            idx = available.index(current)
            if idx + 1 < len(available):
                return available[idx + 1]
        except ValueError:
            pass
        return None

    def summary(self) -> List[dict]:
        return [s.summary() for s in self._sources.values()]

    def all_unavailable(self, priority_order: List[str]) -> bool:
        """检查优先级链中所有数据源是否都不可用"""
        return len(self.get_available_sources(priority_order)) == 0


# 全局单例
_health_manager: Optional[DataSourceHealthManager] = None


def get_health_manager() -> DataSourceHealthManager:
    global _health_manager
    if _health_manager is None:
        _health_manager = DataSourceHealthManager()
    return _health_manager
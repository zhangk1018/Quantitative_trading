#!/usr/bin/env python3
"""
熔断机制 - 保护数据源稳定性
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger('circuit_breaker')


@dataclass
class CircuitBreakerConfig:
    """熔断配置"""
    # 连续失败次数阈值
    failure_threshold: int = 5
    # 熔断时长（秒）
    break_duration: int = 300  # 5分钟
    # 半开状态允许的请求数
    half_open_max_requests: int = 3
    # 半开状态恢复阈值（成功率 > 此值则完全恢复）
    recovery_threshold: float = 0.8
    # 指数退避系数（每次熔断时长翻倍）
    backoff_factor: float = 2.0
    # 最大熔断时长
    max_break_duration: int = 3600  # 1小时


class CircuitBreaker:
    """熔断器 - 状态机实现"""
    
    def __init__(self, config: CircuitBreakerConfig, source_name: str):
        self.config = config
        self.source_name = source_name
        self.state = "closed"  # closed, open, half-open
        self.failure_count = 0
        self.half_open_requests = 0
        self.half_open_successes = 0
        self.open_until: Optional[datetime] = None
        self.current_break_duration = config.break_duration
    
    def record_success(self):
        """记录成功请求"""
        self.failure_count = 0
        if self.state == "half-open":
            self.half_open_successes += 1
            success_rate = self.half_open_successes / self.half_open_requests
            if success_rate >= self.config.recovery_threshold:
                self._transition_to_closed()
            logger.debug(f"半开状态 {self.source_name}: "
                        f"成功 {self.half_open_successes}/{self.half_open_requests} "
                        f"({success_rate:.1%})")
    
    def record_failure(self):
        """记录失败请求"""
        self.failure_count += 1
        logger.debug(f"{self.source_name} 失败次数: {self.failure_count}/{self.config.failure_threshold}")
        
        if self.state == "closed":
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
        elif self.state == "half-open":
            self._transition_to_open()
    
    def allow_request(self) -> bool:
        """判断是否允许请求"""
        if self.state == "closed":
            return True
        elif self.state == "open":
            if datetime.now() >= self.open_until:
                self._transition_to_half_open()
                return True
            remaining = (self.open_until - datetime.now()).total_seconds()
            logger.debug(f"熔断中 {self.source_name}: 剩余 {remaining:.0f}秒")
            return False
        elif self.state == "half-open":
            if self.half_open_requests < self.config.half_open_max_requests:
                self.half_open_requests += 1
                logger.debug(f"半开状态 {self.source_name}: 允许请求 {self.half_open_requests}/{self.config.half_open_max_requests}")
                return True
            return False
        return False
    
    def _transition_to_open(self):
        """切换到打开状态（熔断）"""
        self.state = "open"
        self.open_until = datetime.now() + timedelta(seconds=self.current_break_duration)
        self.half_open_requests = 0
        self.half_open_successes = 0
        # 指数退避：下次熔断时长翻倍
        next_duration = int(self.current_break_duration * self.config.backoff_factor)
        self.current_break_duration = min(next_duration, self.config.max_break_duration)
        logger.warning(f"🔌 熔断 {self.source_name} "
                      f"(失败 {self.failure_count}次), "
                      f"持续 {self.current_break_duration}秒, "
                      f"恢复时间: {self.open_until.strftime('%H:%M:%S')}")
    
    def _transition_to_half_open(self):
        """切换到半开状态（尝试恢复）"""
        self.state = "half-open"
        self.half_open_requests = 0
        self.half_open_successes = 0
        logger.info(f"🔄 {self.source_name} 进入半开状态，开始测试恢复")
    
    def _transition_to_closed(self):
        """切换到关闭状态（恢复正常）"""
        self.state = "closed"
        self.failure_count = 0
        self.current_break_duration = self.config.break_duration
        logger.info(f"✅ {self.source_name} 已恢复正常")
    
    def get_status(self) -> dict:
        """获取熔断器状态"""
        return {
            "source_name": self.source_name,
            "state": self.state,
            "failure_count": self.failure_count,
            "half_open_requests": self.half_open_requests,
            "half_open_successes": self.half_open_successes,
            "open_until": self.open_until.isoformat() if self.open_until else None,
            "current_break_duration": self.current_break_duration
        }

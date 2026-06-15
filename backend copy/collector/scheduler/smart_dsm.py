#!/usr/bin/env python3
"""
智能数据源管理器 - 带性能指标、动态评分和频率限制
"""
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Deque

from collector.datasource.base import (
    BaseDataSource,
    DataSourceManager,
    DataSourceStatus,
    SwitchStrategy
)
from utils.logger import setup_logger
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = setup_logger('smart_dsm')


# 各数据源频率限制配置
DATASOURCE_RATE_LIMITS = {
    'BaoStock': {
        'max_requests_per_minute': 20,  # 官方建议 ≤20次/分钟
        'min_interval': 0.15,           # 建议间隔 0.1-0.2秒
        'burst_size': 3,
    },
    'AKShare': {
        'max_requests_per_minute': 60,  # 东方财富限制约60次/分钟
        'min_interval': 0.1,
        'burst_size': 5,
    },
    'Tushare': {
        'max_requests_per_minute': 30,  # 免费用户限制
        'min_interval': 0.2,
        'burst_size': 2,
    },
    'default': {
        'max_requests_per_minute': 30,
        'min_interval': 0.2,
        'burst_size': 3,
    }
}


class RateLimiter:
    """令牌桶算法实现的频率限制器"""
    
    def __init__(self, rate: float = 1.0, burst: int = 3):
        """
        Args:
            rate: 每秒产生的令牌数
            burst: 令牌桶容量
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def acquire(self, timeout: float = None) -> bool:
        """获取令牌"""
        start_time = time.time()
        
        while True:
            with self.lock:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                
                wait_time = (1 - self.tokens) / self.rate
            
            if timeout is not None:
                elapsed_total = time.time() - start_time
                if elapsed_total + wait_time > timeout:
                    return False
            
            time.sleep(wait_time)


@dataclass
class DataSourceMetrics:
    """数据源性能指标"""
    source_name: str
    total_requests: int = 0
    success_count: int = 0
    failed_count: int = 0
    avg_response_time: float = 0.0
    # 最近N次请求的响应时间，用于滑动窗口计算
    recent_response_times: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    last_success_time: Optional[datetime] = None
    # 动态权重
    dynamic_weight: float = 1.0
    # 学习期标记
    in_learning_period: bool = True
    learning_start: datetime = field(default_factory=datetime.now)
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.success_count / self.total_requests
    
    @property
    def recent_avg_rt(self) -> float:
        """最近平均响应时间"""
        if not self.recent_response_times:
            return 0.0
        return sum(self.recent_response_times) / len(self.recent_response_times)


class DynamicWeightStrategy:
    """动态权重策略"""
    
    # 初始权重（经验值）
    INITIAL_WEIGHTS = {
        'baostock': 3.0,
        'akshare': 2.5,
        'tencent': 2.0,
        'sina': 1.5
    }
    
    # 权重调整系数
    ADJUSTMENT_FACTOR = 0.1  # 每次调整幅度
    MIN_WEIGHT = 0.5         # 最小权重
    MAX_WEIGHT = 5.0         # 最大权重
    LEARNING_PERIOD_DAYS = 7  # 学习期天数
    
    def __init__(self):
        self.current_weights = self.INITIAL_WEIGHTS.copy()
    
    def get_weight(self, source_name: str, metrics: Optional[DataSourceMetrics] = None) -> float:
        """获取数据源权重"""
        # 学习期内用初始权重
        if metrics and metrics.in_learning_period:
            learning_end = metrics.learning_start + timedelta(days=self.LEARNING_PERIOD_DAYS)
            if datetime.now() < learning_end:
                return self.INITIAL_WEIGHTS.get(source_name, 1.0)
            else:
                metrics.in_learning_period = False
        
        # 动态调整
        return self.current_weights.get(source_name, 1.0)
    
    def update_weight(self, source_name: str, performance_score: float):
        """根据性能动态调整权重"""
        # performance_score: 0-100
        
        # 归一化到 -0.5 到 +0.5 范围
        adjustment = (performance_score - 50) / 100 * self.ADJUSTMENT_FACTOR
        
        # 更新权重
        old_weight = self.current_weights.get(source_name, 1.0)
        new_weight = max(self.MIN_WEIGHT, min(self.MAX_WEIGHT, old_weight + adjustment))
        self.current_weights[source_name] = new_weight
        
        logger.info(f"调整 {source_name} 权重: {old_weight:.2f} → {new_weight:.2f} (评分: {performance_score:.1f})")


class SmartDataSourceManager(DataSourceManager):
    """智能数据源管理器 - 带性能指标、熔断机制和频率限制"""
    
    def __init__(
        self,
        sources: Optional[List[Dict[str, Any]]] = None,
        strategy: SwitchStrategy = SwitchStrategy.WEIGHTED,  # 默认用加权策略
        health_check_interval: int = 60,
        auto_recovery: bool = True,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        super().__init__(sources, strategy, health_check_interval, auto_recovery)
        
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.metrics: Dict[str, DataSourceMetrics] = {}
        self.weight_strategy = DynamicWeightStrategy()
        
        # 频率限制器（按数据源名称）
        self.rate_limiters: Dict[str, RateLimiter] = {}
        
        # 初始化熔断器、指标和频率限制器
        for src_info in self.sources:
            source = src_info['source']
            self.circuit_breakers[source.name] = CircuitBreaker(
                self.circuit_breaker_config,
                source.name
            )
            self.metrics[source.name] = DataSourceMetrics(
                source_name=source.name,
                dynamic_weight=self.weight_strategy.INITIAL_WEIGHTS.get(source.name, 1.0)
            )
            
            # 初始化频率限制器
            rate_config = DATASOURCE_RATE_LIMITS.get(source.name, DATASOURCE_RATE_LIMITS['default'])
            rate = rate_config['max_requests_per_minute'] / 60.0
            self.rate_limiters[source.name] = RateLimiter(rate=rate, burst=rate_config['burst_size'])
            logger.info(f"初始化 {source.name} 频率限制器: {rate_config['max_requests_per_minute']}次/分钟")
    
    def _wait_for_rate_limit(self, source_name: str):
        """等待频率限制"""
        if source_name in self.rate_limiters:
            self.rate_limiters[source_name].acquire(timeout=60)
    
    def _execute_with_fallback(self, method_name: str, **kwargs) -> Any:
        """执行方法，带指标采集、熔断和频率限制"""
        start_time = time.time()
        source_used = None
        result = None
        success = False
        
        try:
            # 选择最佳数据源
            if not self.current_source:
                self._select_best_source()
            
            source_used = self.current_source
            source_name = source_used.name
            
            # 检查熔断
            cb = self.circuit_breakers[source_name]
            if not cb.allow_request():
                # 熔断中，切换数据源
                logger.warning(f"{source_name} 熔断中，尝试切换")
                self._switch_to_healthy_source()
                return self._execute_with_fallback(method_name, **kwargs)
            
            # 等待频率限制
            self._wait_for_rate_limit(source_name)
            
            # 执行
            method = getattr(self.current_source, method_name)
            result = method(**kwargs)
            
            # 验证结果
            if result is None or (isinstance(result, list) and not result) or (hasattr(result, 'empty') and result.empty):
                raise Exception("返回空数据")
            
            success = True
            return result
            
        except Exception as e:
            logger.warning(f"{source_used.name if source_used else 'unknown'} 执行 {method_name} 失败: {str(e)}")
            
            # 尝试切换
            if self._switch_to_healthy_source():
                try:
                    # 等待频率限制（切换后的数据源）
                    self._wait_for_rate_limit(self.current_source.name)
                    
                    method = getattr(self.current_source, method_name)
                    result = method(**kwargs)
                    success = True
                    return result
                except Exception:
                    pass
            
            # 都失败了，抛出异常
            raise
        finally:
            if source_used:
                elapsed = time.time() - start_time
                self._record_request(source_used.name, success, elapsed)
    
    def _record_request(self, source_name: str, success: bool, elapsed: float):
        """记录请求指标"""
        metrics = self.metrics[source_name]
        cb = self.circuit_breakers[source_name]
        
        metrics.total_requests += 1
        
        if success:
            metrics.success_count += 1
            metrics.last_success_time = datetime.now()
            cb.record_success()
        else:
            metrics.failed_count += 1
            cb.record_failure()
        
        # 更新响应时间
        metrics.recent_response_times.append(elapsed)
        metrics.avg_response_time = (
            (metrics.avg_response_time * (metrics.total_requests - 1) + elapsed) /
            metrics.total_requests
        )
        
        # 更新动态权重
        score = self._calculate_performance_score(source_name, metrics)
        self.weight_strategy.update_weight(source_name, score)
        metrics.dynamic_weight = self.weight_strategy.get_weight(source_name, metrics)
    
    def _calculate_performance_score(self, source_name: str, metrics: DataSourceMetrics) -> float:
        """计算数据源性能评分（0-100）"""
        base_score = 50.0
        
        # 1. 成功率（占40分）
        base_score += metrics.success_rate * 40
        
        # 2. 响应时间（占30分）
        # 1秒内=30分，每增加1秒减5分，最低0分
        avg_rt = metrics.recent_avg_rt or metrics.avg_response_time
        rt_score = max(0, 30 - max(0, (avg_rt - 1) * 5))
        base_score += rt_score
        
        # 3. 健康状态（占20分）
        health_status = self.health_status.get(source_name, DataSourceStatus.HEALTHY)
        if health_status == DataSourceStatus.HEALTHY:
            base_score += 20
        elif health_status == DataSourceStatus.DEGRADED:
            base_score += 10
        
        # 4. 熔断检查（扣10分）
        cb = self.circuit_breakers[source_name]
        if cb.state != "closed":
            base_score -= 10
        
        return max(0, min(100, base_score))
    
    def _select_best_source(self, cycle: Optional[str] = None):
        """选择最佳数据源"""
        candidates = []
        
        for src_info in self.sources:
            source = src_info['source']
            source_name = source.name
            
            # 1. 检查熔断
            cb = self.circuit_breakers[source_name]
            if cb.state == "open":
                continue
            
            # 2. 检查周期支持
            if cycle and cycle not in source.supported_cycles:
                continue
            
            # 3. 计算综合评分
            metrics = self.metrics[source_name]
            dynamic_weight = self.weight_strategy.get_weight(source_name, metrics)
            performance_score = self._calculate_performance_score(source_name, metrics)
            
            # 综合评分 = 性能评分 * 权重系数
            total_score = performance_score * dynamic_weight
            
            candidates.append((-total_score, source, src_info))  # 负号用于排序
        
        # 按评分排序
        candidates.sort()
        
        if candidates:
            best_score, best_source, best_src_info = candidates[0]
            if self.current_source != best_source:
                self.current_source = best_source
                logger.info(f"切换到 {best_source.name} (评分: {-best_score:.1f})")
            return True
        
        # 没有合适的，尝试任意一个
        if self.sources:
            self.current_source = self.sources[0]['source']
            logger.warning(f"无合适数据源，使用默认: {self.current_source.name}")
            return True
        
        return False
    
    def _switch_to_healthy_source(self) -> bool:
        """切换到一个健康的数据源"""
        for src_info in self.sources:
            source = src_info['source']
            cb = self.circuit_breakers[source.name]
            
            if cb.allow_request():
                self.current_source = source
                logger.info(f"切换到 {source.name}")
                return True
        
        logger.error("无可用数据源")
        return False
    
    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ):
        """获取K线数据，自动选择最佳数据源"""
        self._select_best_source(cycle=cycle)
        return self._execute_with_fallback(
            'get_kline',
            code=code,
            cycle=cycle,
            start_date=start_date,
            end_date=end_date
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取详细统计"""
        stats = super().get_stats()
        
        # 添加熔断器状态
        stats['circuit_breakers'] = {
            name: cb.get_status()
            for name, cb in self.circuit_breakers.items()
        }
        
        # 添加指标
        stats['metrics'] = {}
        for name, m in self.metrics.items():
            stats['metrics'][name] = {
                'total_requests': m.total_requests,
                'success_count': m.success_count,
                'failed_count': m.failed_count,
                'success_rate': f"{m.success_rate:.1%}",
                'avg_response_time': f"{m.avg_response_time:.3f}s",
                'recent_avg_rt': f"{m.recent_avg_rt:.3f}s",
                'dynamic_weight': f"{m.dynamic_weight:.2f}",
                'in_learning_period': m.in_learning_period,
                'performance_score': f"{self._calculate_performance_score(name, m):.1f}"
            }
        
        return stats


def create_smart_dsm(
    strategy: str = 'weighted',
    auto_recovery: bool = True,
    health_check_interval: int = 60,
    cb_config: Optional[CircuitBreakerConfig] = None
) -> SmartDataSourceManager:
    """
    创建智能数据源管理器的便捷函数
    """
    from collector.datasource.baostock import BaostockDataSource
    from collector.datasource.akshare import AkshareDataSource
    from collector.datasource.sina import SinaDataSource
    from collector.datasource.tencent import TencentDataSource
    
    # 配置多数据源
    sources = [
        {'source': BaostockDataSource(), 'priority': 0},
        {'source': AkshareDataSource(), 'priority': 1},
        {'source': TencentDataSource(), 'priority': 2},
        {'source': SinaDataSource(), 'priority': 3}
    ]
    
    strategy_enum = {
        'failover': SwitchStrategy.FAILOVER,
        'round_robin': SwitchStrategy.ROUND_ROBIN,
        'weighted': SwitchStrategy.WEIGHTED
    }.get(strategy, SwitchStrategy.WEIGHTED)
    
    return SmartDataSourceManager(
        sources=sources,
        strategy=strategy_enum,
        auto_recovery=auto_recovery,
        health_check_interval=health_check_interval,
        circuit_breaker_config=cb_config
    )

#!/usr/bin/env python3
"""
数据源抽象基类 - 定义统一接口
"""
import abc
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import time
from utils.logger import setup_logger

logger = setup_logger('datasource_manager')


class BaseDataSource(abc.ABC):
    """
    数据源抽象基类
    
    所有数据源必须实现以下接口：
    - get_stock_list(): 获取股票列表
    - get_kline(): 获取K线数据
    """
    
    @abc.abstractmethod
    def connect(self) -> bool:
        """建立连接"""
        pass
    
    @abc.abstractmethod
    def disconnect(self) -> bool:
        """断开连接"""
        pass
    
    @abc.abstractmethod
    def get_stock_list(self) -> pd.DataFrame:
        """
        获取股票列表
        
        返回DataFrame，包含字段：
        - code: 股票代码（格式：sh.600000 或 sz.000001）
        - name: 股票名称
        - exchange: 交易所
        - industry: 行业
        - list_date: 上市日期
        - delist_date: 退市日期（如有）
        """
        pass
    
    @abc.abstractmethod
    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取K线数据
        
        Args:
            code: 股票代码
            cycle: 周期，支持 daily/min5/min15/min30/min60
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
        
        返回DataFrame，包含字段：
        - code: 股票代码
        - trade_date: 交易日期（日线：YYYY-MM-DD，分钟线：YYYY-MM-DD HH:MM:SS）
        - open: 开盘价
        - high: 最高价
        - low: 最低价
        - close: 收盘价
        - volume: 成交量
        - amount: 成交额
        - cycle: 周期标识
        """
        pass
    
    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = 'SH'
    ) -> pd.DataFrame:
        """
        获取交易日历（可选实现）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            exchange: 交易所
        
        Returns:
            DataFrame: 包含 cal_date, is_open, exchange 字段
        """
        return pd.DataFrame()
    
    def get_next_trade_date(self, last_date: str, exchange: str = 'SH') -> Optional[str]:
        """
        获取下一个交易日（可选实现）
        
        Args:
            last_date: 最后日期
            exchange: 交易所
        
        Returns:
            下一个交易日日期
        """
        return None
    
    def fetch_market_snapshot(self) -> pd.DataFrame:
        """
        获取市场快照（可选实现）
        
        Returns:
            DataFrame: 包含最新行情数据
        """
        return pd.DataFrame()
    
    def health_check(self) -> bool:
        """
        健康检查（可选实现）
        
        Returns:
            是否健康
        """
        try:
            # 默认实现：尝试获取股票列表来验证连接
            df = self.get_stock_list()
            return df is not None and not df.empty
        except:
            return False
    
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """数据源名称"""
        pass
    
    @property
    @abc.abstractmethod
    def requires_token(self) -> bool:
        """是否需要Token"""
        pass
    
    @property
    @abc.abstractmethod
    def supported_cycles(self) -> List[str]:
        """支持的周期列表"""
        pass


# 切换策略枚举
class SwitchStrategy(Enum):
    FAILOVER = 'failover'        # 故障切换：主数据源失败时切换到备用
    ROUND_ROBIN = 'round_robin'  # 轮询：按顺序轮询所有数据源
    WEIGHTED = 'weighted'        # 加权：按权重分配请求


class DataSourceStatus(Enum):
    """数据源状态"""
    HEALTHY = 'healthy'
    DEGRADED = 'degraded'
    UNHEALTHY = 'unhealthy'


class DataSourceManager:
    """
    数据源管理器 - 支持多数据源管理和智能切换策略
    
    功能：
    - 支持多种切换策略（故障切换、轮询、加权）
    - 健康检查机制
    - 自动恢复主数据源
    - 数据源优先级配置
    - 切换日志和监控
    """
    
    def __init__(
        self,
        sources: Optional[List[Dict[str, Any]]] = None,
        strategy: SwitchStrategy = SwitchStrategy.FAILOVER,
        health_check_interval: int = 60,  # 健康检查间隔（秒）
        auto_recovery: bool = True  # 是否自动恢复主数据源
    ):
        """
        Args:
            sources: 数据源配置列表，每个元素包含：
                - source: BaseDataSource实例
                - weight: 权重（用于加权策略），默认1
                - priority: 优先级（用于故障切换），默认0（数字越小优先级越高）
            strategy: 切换策略
            health_check_interval: 健康检查间隔（秒）
            auto_recovery: 是否自动恢复主数据源
        """
        # 处理旧的初始化方式（兼容原有代码）
        if sources is None or len(sources) == 0:
            # 使用默认配置
            from collector.datasource.baostock import BaostockDataSource
            from collector.datasource.akshare import AkshareDataSource
            sources = [
                {'source': BaostockDataSource(), 'weight': 1, 'priority': 0},
                {'source': AkshareDataSource(), 'weight': 1, 'priority': 1}
            ]
        
        self.sources = sorted(sources, key=lambda x: x.get('priority', 0))
        self.strategy = strategy
        self.health_check_interval = health_check_interval
        self.auto_recovery = auto_recovery
        
        self.current_source = None
        self.current_source_index = 0
        self.fallback_count = 0
        self.last_health_check = 0
        self.health_status = {}  # 存储各数据源健康状态
        self.switch_history = []  # 切换历史记录
        
        # 初始化健康状态
        for idx, src in enumerate(self.sources):
            self.health_status[src['source'].name] = DataSourceStatus.HEALTHY
    
    @property
    def primary_source(self):
        """主数据源（优先级最高的）"""
        return self.sources[0]['source'] if self.sources else None
    
    @property
    def backup_sources(self):
        """备用数据源列表"""
        return [s['source'] for s in self.sources[1:]] if len(self.sources) > 1 else []
    
    def connect(self) -> bool:
        """连接数据源（根据策略选择）"""
        logger.info(f"数据源管理器初始化，策略: {self.strategy.value}")
        
        if self.strategy == SwitchStrategy.FAILOVER:
            # 故障切换策略：优先连接主数据源
            return self._connect_failover()
        elif self.strategy == SwitchStrategy.ROUND_ROBIN:
            # 轮询策略：从第一个开始
            return self._connect_round_robin()
        elif self.strategy == SwitchStrategy.WEIGHTED:
            # 加权策略：选择权重最高的
            return self._connect_weighted()
        
        return False
    
    def _connect_failover(self) -> bool:
        """故障切换模式连接"""
        # 先尝试主数据源
        for idx, src_info in enumerate(self.sources):
            source = src_info['source']
            if self._try_connect_source(source, idx):
                return True
        
        return False
    
    def _connect_round_robin(self) -> bool:
        """轮询模式连接"""
        num_sources = len(self.sources)
        for i in range(num_sources):
            idx = (self.current_source_index + i) % num_sources
            source = self.sources[idx]['source']
            if self._try_connect_source(source, idx):
                return True
        
        return False
    
    def _connect_weighted(self) -> bool:
        """加权模式连接"""
        # 按权重排序，优先尝试权重大的
        sorted_sources = sorted(self.sources, key=lambda x: -x.get('weight', 1))
        for idx, src_info in enumerate(sorted_sources):
            source = src_info['source']
            # 找到原始索引
            orig_idx = next(i for i, s in enumerate(self.sources) if s['source'] == source)
            if self._try_connect_source(source, orig_idx):
                return True
        
        return False
    
    def _try_connect_source(self, source, index) -> bool:
        """尝试连接指定数据源"""
        try:
            if source.connect():
                self.current_source = source
                self.current_source_index = index
                self.health_status[source.name] = DataSourceStatus.HEALTHY
                logger.info(f"✅ 成功连接数据源: {source.name}")
                return True
            else:
                self.health_status[source.name] = DataSourceStatus.UNHEALTHY
                logger.warning(f"⚠️ 无法连接数据源: {source.name}")
                return False
        except Exception as e:
            self.health_status[source.name] = DataSourceStatus.UNHEALTHY
            logger.error(f"❌ 连接数据源失败 {source.name}: {str(e)}")
            return False
    
    def disconnect(self):
        """断开所有数据源连接"""
        for src_info in self.sources:
            try:
                src_info['source'].disconnect()
            except Exception as e:
                logger.warning(f"断开数据源 {src_info['source'].name} 失败: {str(e)}")
        
        self.current_source = None
        self.current_source_index = 0
        logger.info("所有数据源已断开")
    
    def _perform_health_check(self):
        """执行健康检查（定期）"""
        now = time.time()
        if now - self.last_health_check < self.health_check_interval:
            return
        
        self.last_health_check = now
        
        for src_info in self.sources:
            source = src_info['source']
            try:
                if source.health_check():
                    self.health_status[source.name] = DataSourceStatus.HEALTHY
                else:
                    self.health_status[source.name] = DataSourceStatus.DEGRADED
            except Exception as e:
                self.health_status[source.name] = DataSourceStatus.UNHEALTHY
                logger.warning(f"健康检查失败 {source.name}: {str(e)}")
        
        # 自动恢复主数据源
        if self.auto_recovery and self.current_source != self.primary_source:
            if self.health_status.get(self.primary_source.name) == DataSourceStatus.HEALTHY:
                self._switch_to_source(self.primary_source, 0, "自动恢复")
    
    def _switch_to_source(self, source, index, reason):
        """切换到指定数据源"""
        try:
            # 断开当前连接
            if self.current_source and self.current_source != source:
                self.current_source.disconnect()
            
            # 连接新数据源
            if source.connect():
                old_source_name = self.current_source.name if self.current_source else "None"
                self.current_source = source
                self.current_source_index = index
                self.fallback_count += 1
                
                # 记录切换历史
                self.switch_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'from_source': old_source_name,
                    'to_source': source.name,
                    'reason': reason,
                    'fallback_count': self.fallback_count
                })
                
                # 保留最近100条切换记录
                if len(self.switch_history) > 100:
                    self.switch_history = self.switch_history[-100:]
                
                logger.warning(f"🔄 数据源切换: {old_source_name} -> {source.name} (原因: {reason})")
                return True
            else:
                logger.error(f"❌ 切换到 {source.name} 失败")
                return False
        except Exception as e:
            logger.error(f"❌ 切换到 {source.name} 异常: {str(e)}")
            return False
    
    def _execute_with_fallback(self, method_name: str, **kwargs) -> Any:
        """执行方法并处理故障切换"""
        if not self.current_source:
            raise RuntimeError("未连接到数据源")
        
        # 先执行健康检查
        self._perform_health_check()
        
        try:
            method = getattr(self.current_source, method_name)
            result = method(**kwargs)
            
            # 验证结果
            if isinstance(result, pd.DataFrame) and result.empty:
                # 空结果也尝试切换
                return self._try_fallback(method_name, Exception("返回空数据"), **kwargs)
            
            return result
        
        except Exception as e:
            logger.warning(f"当前数据源 {self.current_source.name} 执行 {method_name} 失败: {str(e)}")
            return self._try_fallback(method_name, e, **kwargs)
    
    def _try_fallback(self, method_name: str, original_error: Exception, **kwargs):
        """尝试切换到备用数据源"""
        if self.strategy == SwitchStrategy.FAILOVER:
            return self._failover_fallback(method_name, original_error, **kwargs)
        elif self.strategy == SwitchStrategy.ROUND_ROBIN:
            return self._round_robin_fallback(method_name, original_error, **kwargs)
        elif self.strategy == SwitchStrategy.WEIGHTED:
            return self._weighted_fallback(method_name, original_error, **kwargs)
        
        raise original_error
    
    def _failover_fallback(self, method_name: str, original_error: Exception, **kwargs):
        """故障切换模式的降级处理"""
        # 按优先级尝试备用数据源
        for idx, src_info in enumerate(self.sources):
            if idx == self.current_source_index:
                continue  # 跳过当前数据源
            
            source = src_info['source']
            # 优先选择健康的数据源
            if self.health_status.get(source.name) == DataSourceStatus.UNHEALTHY:
                continue
            
            try:
                if self._switch_to_source(source, idx, str(original_error)):
                    method = getattr(source, method_name)
                    return method(**kwargs)
            except Exception as e:
                self.health_status[source.name] = DataSourceStatus.UNHEALTHY
                continue
        
        raise original_error
    
    def _round_robin_fallback(self, method_name: str, original_error: Exception, **kwargs):
        """轮询模式的降级处理"""
        num_sources = len(self.sources)
        for i in range(1, num_sources):
            idx = (self.current_source_index + i) % num_sources
            source = self.sources[idx]['source']
            
            try:
                if self._switch_to_source(source, idx, "轮询切换"):
                    method = getattr(source, method_name)
                    return method(**kwargs)
            except Exception as e:
                continue
        
        raise original_error
    
    def _weighted_fallback(self, method_name: str, original_error: Exception, **kwargs):
        """加权模式的降级处理"""
        # 按权重排序（排除当前数据源）
        available = sorted(
            [(i, s) for i, s in enumerate(self.sources) if i != self.current_source_index],
            key=lambda x: -x[1].get('weight', 1)
        )
        
        for idx, src_info in available:
            source = src_info['source']
            try:
                if self._switch_to_source(source, idx, "加权切换"):
                    method = getattr(source, method_name)
                    return method(**kwargs)
            except Exception as e:
                continue
        
        raise original_error
    
    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        return self._execute_with_fallback('get_stock_list')
    
    def get_kline(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取K线数据"""
        return self._execute_with_fallback('get_kline', code=code, cycle=cycle, 
                                          start_date=start_date, end_date=end_date)
    
    def get_trade_calendar(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exchange: str = 'SH'
    ) -> pd.DataFrame:
        """获取交易日历"""
        return self._execute_with_fallback('get_trade_calendar', start_date=start_date, 
                                          end_date=end_date, exchange=exchange)
    
    def get_next_trade_date(self, last_date: str, exchange: str = 'SH') -> Optional[str]:
        """获取下一个交易日"""
        return self._execute_with_fallback('get_next_trade_date', last_date=last_date, exchange=exchange)
    
    def fetch_market_snapshot(self) -> pd.DataFrame:
        """获取市场快照"""
        return self._execute_with_fallback('fetch_market_snapshot')
    
    def switch_strategy(self, strategy: SwitchStrategy):
        """切换策略"""
        logger.info(f"切换策略: {self.strategy.value} -> {strategy.value}")
        self.strategy = strategy
    
    def get_stats(self) -> Dict[str, Any]:
        """获取数据源统计信息"""
        return {
            'current_source': self.current_source_name,
            'strategy': self.strategy.value,
            'fallback_count': self.fallback_count,
            'total_sources': len(self.sources),
            'health_status': {k: v.value for k, v in self.health_status.items()},
            'auto_recovery': self.auto_recovery,
            'last_switch_time': self.switch_history[-1]['timestamp'] if self.switch_history else None
        }
    
    def get_switch_history(self) -> List[Dict[str, Any]]:
        """获取切换历史"""
        return self.switch_history
    
    def get_available_cycles(self) -> List[str]:
        """获取当前数据源支持的周期"""
        if self.current_source:
            return self.current_source.supported_cycles
        return []
    
    @property
    def current_source_name(self) -> str:
        """当前数据源名称"""
        return self.current_source.name if self.current_source else "未连接"
    
    @property
    def has_fallback(self) -> bool:
        """是否已切换到备用数据源"""
        return self.fallback_count > 0
    
    @property
    def is_primary_active(self) -> bool:
        """主数据源是否活跃"""
        return self.current_source == self.primary_source


# 兼容旧的初始化方式
class LegacyDataSourceManager(DataSourceManager):
    """
    兼容旧版的数据源管理器
    
    保持原有接口不变，内部使用新的实现
    """
    
    def __init__(self, primary: BaseDataSource, backups: Optional[List[BaseDataSource]] = None):
        sources = [{'source': primary, 'weight': 1, 'priority': 0}]
        if backups:
            for i, backup in enumerate(backups):
                sources.append({'source': backup, 'weight': 1, 'priority': i + 1})
        
        super().__init__(sources=sources, strategy=SwitchStrategy.FAILOVER)


# 便捷工厂函数
def create_dsm(
    strategy: str = 'failover',
    auto_recovery: bool = True,
    health_check_interval: int = 60
) -> DataSourceManager:
    """
    创建数据源管理器的便捷函数
    
    Args:
        strategy: 切换策略 ('failover', 'round_robin', 'weighted')
        auto_recovery: 是否自动恢复主数据源
        health_check_interval: 健康检查间隔（秒）
    
    Returns:
        DataSourceManager实例
    """
    from collector.datasource.tushare import TushareDataSource
    from collector.datasource.baostock import BaostockDataSource
    from collector.datasource.akshare import AkshareDataSource
    from collector.datasource.sina import SinaDataSource
    from collector.datasource.tencent import TencentDataSource
    
    # 配置多数据源：Tushare 主，Baostock/Akshare/Tencent/Sina 备用
    sources = [
        {'source': TushareDataSource(), 'weight': 3, 'priority': 0},   # 主数据源（优先级最高）
        {'source': BaostockDataSource(), 'weight': 2, 'priority': 1},   # 备用1
        {'source': AkshareDataSource(), 'weight': 1, 'priority': 2},    # 备用2
        {'source': TencentDataSource(), 'weight': 1, 'priority': 3},    # 备用3
        {'source': SinaDataSource(), 'weight': 1, 'priority': 4}        # 备用4
    ]
    
    strategy_enum = {
        'failover': SwitchStrategy.FAILOVER,
        'round_robin': SwitchStrategy.ROUND_ROBIN,
        'weighted': SwitchStrategy.WEIGHTED
    }.get(strategy, SwitchStrategy.FAILOVER)
    
    return DataSourceManager(
        sources=sources,
        strategy=strategy_enum,
        auto_recovery=auto_recovery,
        health_check_interval=health_check_interval
    )


# 测试代码
if __name__ == '__main__':
    # 创建数据源管理器
    dsm = create_dsm(strategy='failover')
    
    print(f"初始化数据源管理器，策略: {dsm.strategy.value}")
    print(f"数据源数量: {len(dsm.sources)}")
    
    # 连接
    if dsm.connect():
        print(f"✅ 连接成功，当前数据源: {dsm.current_source_name}")
        
        # 获取统计信息
        stats = dsm.get_stats()
        print(f"\n数据源统计:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        
        # 测试获取股票列表
        try:
            stocks = dsm.get_stock_list()
            print(f"\n获取股票列表成功，共 {len(stocks)} 只股票")
        except Exception as e:
            print(f"\n获取股票列表失败: {str(e)}")
        
        # 断开连接
        dsm.disconnect()
        print("\n✅ 数据源已断开")
    else:
        print("❌ 连接失败")
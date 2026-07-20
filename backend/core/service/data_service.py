#!/usr/bin/env python3
"""
数据服务层 - 统一对外接口

提供：
- 股票列表更新
- 单股票/单周期数据下载（支持复权）
- 全量自动更新（带限流控制和断点续传）
- 数据查询接口（带缓存）
- 交易日历管理
- 多数据源自动降级
- 回测/实盘双模式支持
"""
import time
import random
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from collector.datasource.base import DataSourceManager, LegacyDataSourceManager
from collector.datasource.baostock import BaostockDataSource
from collector.datasource.tushare import TushareDataSource
from utils.storage_factory import StorageFactory
from clean.processor.data_processor import DataProcessor
from utils.logger import setup_logger
from utils.config import config
import json
import os
from functools import wraps

logger = setup_logger('data_service')

# 快照存储路径
# 从 src/service/data_service.py 向上三层目录到项目根目录
SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'snapshot', 'latest')

# 缓存配置
CACHE_CONFIG = {
    'enabled': config.cache.get('enabled', True),
    'default_ttl': config.cache.get('default_ttl', 300),  # 默认缓存5分钟
    'quotes_ttl': config.cache.get('quotes_ttl', 60),     # 行情数据缓存1分钟
    'indicators_ttl': config.cache.get('indicators_ttl', 300),  # 指标缓存5分钟
    'stock_list_ttl': config.cache.get('stock_list_ttl', 3600),  # 股票列表缓存1小时
    'max_size': config.cache.get('max_size', 1000)  # 最大缓存条目数
}


class DataCache:
    """数据缓存管理器"""
    
    def __init__(self):
        self.cache = {}
        self.hit_count = 0
        self.miss_count = 0
    
    def _get_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        return f"{prefix}:{json.dumps(kwargs, sort_keys=True)}"
    
    def get(self, prefix: str, **kwargs) -> Optional[Any]:
        """获取缓存数据"""
        key = self._get_key(prefix, **kwargs)
        
        if key not in self.cache:
            self.miss_count += 1
            return None
        
        entry = self.cache[key]
        now = time.time()
        
        # 检查是否过期
        if now - entry['timestamp'] > entry['ttl']:
            del self.cache[key]
            self.miss_count += 1
            return None
        
        self.hit_count += 1
        return entry['data']
    
    def set(self, prefix: str, data: Any, ttl: int = None, **kwargs):
        """设置缓存数据"""
        # 检查缓存大小
        if len(self.cache) >= CACHE_CONFIG['max_size']:
            # 移除最旧的缓存
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        key = self._get_key(prefix, **kwargs)
        self.cache[key] = {
            'data': data,
            'timestamp': time.time(),
            'ttl': ttl or CACHE_CONFIG['default_ttl']
        }
    
    def clear(self, prefix: str = None):
        """清除缓存"""
        if prefix:
            keys_to_remove = [k for k in self.cache.keys() if k.startswith(prefix)]
            for k in keys_to_remove:
                del self.cache[k]
        else:
            self.cache.clear()
    
    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self.hit_count + self.miss_count
        hit_rate = self.hit_count / total * 100 if total > 0 else 0
        return {
            'hit_count': self.hit_count,
            'miss_count': self.miss_count,
            'hit_rate': f"{hit_rate:.2f}%",
            'cache_size': len(self.cache)
        }


def cache_decorator(prefix: str, ttl: int = None):
    """缓存装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not CACHE_CONFIG['enabled']:
                return func(self, *args, **kwargs)
            
            # 构建缓存键参数
            cache_kwargs = {}
            for i, arg in enumerate(args):
                if arg is not None:
                    cache_kwargs[f'arg{i}'] = arg
            
            # 获取缓存
            result = self.cache.get(prefix, **cache_kwargs)
            if result is not None:
                logger.debug(f"缓存命中: {prefix}")
                return result
            
            # 执行函数
            result = func(self, *args, **kwargs)
            
            # 设置缓存（只缓存非空DataFrame）
            if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                self.cache.set(prefix, result, ttl, **cache_kwargs)
            
            return result
        return wrapper
    return decorator


class RequestRateLimiter:
    """请求限流控制器"""
    
    def __init__(self):
        self.last_request_time = 0
        self.request_count = 0
        self.window_start = 0
        self.request_interval = config.datasource.get('request_interval', 0.3)
        self.max_requests_per_minute = config.datasource.get('max_requests_per_minute', 120)
        self.random_jitter = config.datasource.get('random_jitter', True)
    
    def wait(self):
        """执行限流等待"""
        now = time.time()
        
        # 检查时间窗口
        if now - self.window_start >= 60:
            self.window_start = now
            self.request_count = 0
        
        # 检查每分钟请求数
        if self.request_count >= self.max_requests_per_minute:
            sleep_time = 60 - (now - self.window_start)
            logger.debug(f"请求超限，等待 {sleep_time:.2f} 秒")
            time.sleep(sleep_time)
            self.window_start = time.time()
            self.request_count = 0
        
        # 基础间隔控制
        elapsed = now - self.last_request_time
        if elapsed < self.request_interval:
            sleep_time = self.request_interval - elapsed
            
            # 添加随机抖动避免请求峰值
            if self.random_jitter:
                jitter = random.uniform(-0.05, 0.1)
                sleep_time = max(0, sleep_time + jitter)
            
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1


class DataService:
    """统一数据服务接口"""
    
    # 运行模式
    MODE_BACKTEST = 'backtest'    # 回测模式
    MODE_LIVE = 'live'            # 实盘模式
    
    def __init__(self, db_path: str = None, mode: str = MODE_BACKTEST):
        # 使用存储工厂创建存储实例
        self.storage = StorageFactory.create_storage(config.storage)
        self.processor = DataProcessor()
        self.rate_limiter = RequestRateLimiter()
        
        # 初始化缓存
        self.cache = DataCache()
        
        # 初始化数据源管理器（主备切换）：Baostock 主，Tushare 备
        primary = BaostockDataSource()
        backup = TushareDataSource()
        self.dsm = LegacyDataSourceManager(primary=primary, backups=[backup])
        
        # 更新统计
        self.update_stats = {
            'success_count': 0,
            'fail_count': 0,
            'total_stocks': 0,
            'updated_cycles': [],
            'start_time': None,
            'end_time': None,
            'fallback_count': 0  # 降级切换次数
        }
        
        # 当前复权模式
        self.adjust_type = config.datasource.get('adjust_type', 'none')  # none, qfq, hfq
        
        # 当前任务ID
        self.current_task_id = None
        
        # 当前运行模式（回测/实盘）
        self.mode = mode
        logger.info(f"数据服务初始化模式: {mode}")
    
    def set_mode(self, mode: str):
        """设置运行模式"""
        if mode not in [self.MODE_BACKTEST, self.MODE_LIVE]:
            raise ValueError(f"无效模式: {mode}，仅支持 {self.MODE_BACKTEST} 和 {self.MODE_LIVE}")
        self.mode = mode
        logger.info(f"运行模式切换为: {mode}")
    
    def get_mode(self) -> str:
        """获取当前运行模式"""
        return self.mode
    
    def is_backtest_mode(self) -> bool:
        """是否为回测模式"""
        return self.mode == self.MODE_BACKTEST
    
    def is_live_mode(self) -> bool:
        """是否为实盘模式"""
        return self.mode == self.MODE_LIVE
    
    def connect(self) -> bool:
        """建立所有连接"""
        logger.info("正在初始化数据服务...")
        
        # 连接数据库
        if not self.storage.connect():
            logger.error("数据库连接失败")
            return False
        
        # 连接数据源（支持自动降级）
        if not self.dsm.connect():
            logger.error("数据源连接失败")
            self.storage.disconnect()
            return False
        
        logger.info(f"✅ 数据服务初始化完成，当前数据源: {self.dsm.current_source_name}")
        
        # 如果发生了降级切换，记录告警
        if self.dsm.has_fallback:
            logger.warning(f"⚠️ 已切换到备用数据源: {self.dsm.current_source_name}")
        
        return True
    
    def disconnect(self):
        """断开所有连接"""
        self.dsm.disconnect()
        self.storage.disconnect()
        logger.info("数据服务已关闭")
    
    def update_stock_basic(self) -> bool:
        """更新股票列表"""
        logger.info("开始更新股票列表...")
        
        try:
            # 获取股票列表（支持自动降级）
            df = self.dsm.get_stock_list()
            
            if df.empty:
                logger.warning("未获取到股票列表")
                return False
            
            # 保存到数据库
            self.storage.save_stock_basic(df)
            
            logger.info(f"✅ 股票列表更新完成，共 {len(df)} 只股票")
            return True
        
        except Exception as e:
            logger.error(f"股票列表更新失败: {str(e)}")
            return False
    
    def update_trade_calendar(self, years: int = 5) -> bool:
        """
        更新交易日历
        
        Args:
            years: 同步未来多少年的日历（默认5年）
        
        Returns:
            是否成功
        """
        logger.info("开始更新交易日历...")
        
        try:
            # 计算日期范围
            end_date = (datetime.now() + timedelta(days=years * 365)).strftime('%Y-%m-%d')
            
            # 获取交易日历（支持自动降级）
            df = self.dsm.get_trade_calendar(end_date=end_date)
            
            if df.empty:
                logger.warning("未获取到交易日历")
                return False
            
            # 保存到数据库
            self.storage.save_trade_calendar(df)
            
            logger.info(f"✅ 交易日历更新完成，共 {len(df)} 天")
            return True
        
        except Exception as e:
            logger.error(f"交易日历更新失败: {str(e)}")
            return False
    
    def _check_need_update(self, code: str, cycle: str) -> Optional[str]:
        """
        检查是否需要更新（带交易日历校验）
        
        Args:
            code: 股票代码
            cycle: 周期
        
        Returns:
            需要更新的起始日期，如果无需更新则返回None，如果需要从头下载返回空字符串""
        """
        # 获取数据库最后日期
        last_date = self.storage.get_last_date(code, cycle)
        
        if not last_date:
            # 没有历史数据，需要从头开始下载
            return ""
        
        # 提取日期部分（去除时间）
        last_date_only = last_date.split(' ')[0]
        
        # 尝试从本地日历获取下一个交易日
        next_trade_date = self.storage.get_next_trade_date(last_date_only)
        
        if next_trade_date is None:
            # 日历中没有找到，可能是最新的或者日历未同步
            # 再尝试从数据源获取
            try:
                next_trade_date = self.dsm.get_next_trade_date(last_date_only)
            except Exception:
                # 如果都失败，使用简单计算
                next_trade_date = self._simple_next_trade_date(last_date_only)
        
        if next_trade_date is None:
            logger.debug(f"股票 {code} {cycle} 数据已是最新，无需更新")
            return None
        
        # 检查是否超过今天
        if next_trade_date > datetime.now().strftime('%Y-%m-%d'):
            logger.debug(f"股票 {code} {cycle} 下一个交易日 {next_trade_date} 未到")
            return None
        
        return next_trade_date
    
    def _simple_next_trade_date(self, last_date: str) -> Optional[str]:
        """简单计算下一个交易日（备用方案）"""
        try:
            last_dt = datetime.strptime(last_date, '%Y-%m-%d')
            today = datetime.now()
            
            for i in range(1, 15):
                next_dt = last_dt + timedelta(days=i)
                if next_dt.weekday() >= 5:
                    continue
                if next_dt.date() > today.date():
                    return None
                return next_dt.strftime('%Y-%m-%d')
            
            return None
        except Exception:
            return None
    
    def download_quotes(
        self,
        code: str,
        cycle: str = 'daily',
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: Optional[str] = None
    ) -> bool:
        """
        下载单股票单周期数据（带交易日历校验和复权支持）
        
        Args:
            code: 股票代码
            cycle: 周期（daily/min5/min15/min30/min60）
            start_date: 开始日期（可选，默认从数据库最后日期+1开始）
            end_date: 结束日期（可选，默认今天）
            adjust: 复权类型（none/qfq/hfq，默认使用配置）
        
        Returns:
            是否成功
        """
        # 使用配置的复权类型，除非显式指定
        if adjust is None:
            adjust = self.adjust_type
        
        try:
            # 如果没有指定起始日期，使用日历校验
            if not start_date:
                start_date = self._check_need_update(code, cycle)
                
                # start_date 为 None 表示无需更新（数据已是最新）
                if start_date is None:
                    logger.debug(f"股票 {code} {cycle} 数据已是最新，无需更新")
                    return True
                # start_date 为空字符串 "" 表示需要从头下载（没有历史数据）
            
            logger.debug(f"下载 {code} {cycle} [{adjust}]: {start_date} -> {end_date}")
            
            # 限流控制
            self.rate_limiter.wait()
            
            # 获取K线数据（支持复权）
            df = self.dsm.get_kline(code, cycle, start_date, end_date)
            
            if df.empty:
                logger.debug(f"股票 {code} {cycle} 无新数据")
                return True
            
            # 如果需要复权，执行复权计算
            if adjust != 'none':
                df = self._adjust_prices(df, adjust)
            
            # 结构化数据质量校验
            initial_count = len(df)
            df = self.processor.process(df)
            
            if df.empty:
                logger.debug(f"股票 {code} {cycle} 清洗后无有效数据")
                return True
            
            # 记录过滤统计
            filtered_count = initial_count - len(df)
            if filtered_count > 0:
                logger.debug(f"股票 {code} {cycle}: 过滤 {filtered_count} 条异常数据")
            
            # 保存数据（使用带事务的批量写入）
            self.storage.save_quotes(df)
            
            logger.debug(f"✅ {code} {cycle}[{adjust}]: 新增 {len(df)} 条数据")
            return True
        
        except Exception as e:
            logger.error(f"下载 {code} {cycle} 失败: {str(e)}")
            
            # 检查是否需要降级重试
            if self.dsm.has_fallback:
                logger.warning(f"已切换到备用数据源，重试中...")
                return self.download_quotes(code, cycle, start_date, end_date, adjust)
            
            return False
    
    def _adjust_prices(self, df: pd.DataFrame, adjust_type: str) -> pd.DataFrame:
        """
        执行复权计算
        
        Args:
            df: 原始K线数据
            adjust_type: 复权类型（qfq-前复权/hfq-后复权）
        
        Returns:
            复权后的数据
        """
        if adjust_type not in ['qfq', 'hfq']:
            return df
        
        try:
            # 计算复权因子
            df = df.copy().sort_values('trade_date')
            
            if adjust_type == 'qfq':
                # 前复权：从后向前计算
                df = df.iloc[::-1]
                factor = 1.0
                factors = []
                
                for _, row in df.iterrows():
                    factors.append(factor)
                    # 前复权：使用前收盘价计算涨跌幅
                    if row['close'] > 0 and not pd.isna(row['close']) and row['pre_close'] > 0 and not pd.isna(row['pre_close']):
                        factor *= (1 + (row['close'] - row['pre_close']) / row['pre_close'])
                    elif row['close'] > 0 and not pd.isna(row['close']):
                        # 如果无前收盘价数据，使用当日涨跌幅作为近似
                        factor *= (1 + (row['close'] - row['open']) / row['open'])
                
                df['adjust_factor'] = factors[::-1]
                df['adjust_factor'] = df['adjust_factor'] / df['adjust_factor'].iloc[0]
                
            else:
                # 后复权：从前向后计算
                factor = 1.0
                factors = []
                
                for _, row in df.iterrows():
                    factors.append(factor)
                    if row['close'] > 0 and not pd.isna(row['close']) and row['pre_close'] > 0 and not pd.isna(row['pre_close']):
                        factor *= (1 + (row['close'] - row['pre_close']) / row['pre_close'])
                    elif row['close'] > 0 and not pd.isna(row['close']):
                        # 如果无前收盘价数据，使用当日涨跌幅作为近似
                        factor *= (1 + (row['close'] - row['open']) / row['open'])
                
                df['adjust_factor'] = factors
            
            # 应用复权因子
            df['open'] = df['open'] * df['adjust_factor']
            df['high'] = df['high'] * df['adjust_factor']
            df['low'] = df['low'] * df['adjust_factor']
            df['close'] = df['close'] * df['adjust_factor']
            
            # 保留两位小数
            df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].round(2)
            
            logger.debug(f"复权完成: {adjust_type}, 因子范围: [{df['adjust_factor'].min():.4f}, {df['adjust_factor'].max():.4f}]")
            
            return df
        
        except Exception as e:
            logger.warning(f"复权计算失败，使用原始数据: {str(e)}")
            return df
    
    def download_all(self, threads: int = 1, cycles: Optional[List[str]] = None, resume: bool = True) -> dict:
        """
        全量自动更新所有股票所有周期（带限流控制和断点续传）
        
        Args:
            threads: 线程数（建议1-2，避免被限流）
            cycles: 指定周期列表，默认所有周期
            resume: 是否启用断点续传
        
        Returns:
            更新统计结果
        """
        logger.info("=" * 60)
        logger.info("开始全量自动更新")
        logger.info("=" * 60)
        
        # 重置统计
        self.update_stats = {
            'success_count': 0,
            'fail_count': 0,
            'total_stocks': 0,
            'updated_cycles': cycles or ['daily', 'min5', 'min15', 'min30', 'min60'],
            'start_time': datetime.now(),
            'end_time': None,
            'fallback_count': 0,
            'resumed_from': None  # 断点续传的起始位置
        }
        
        # 生成任务ID
        self.current_task_id = f"update_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # 获取股票列表
            stocks = self.storage.get_stock_list()
            
            if stocks.empty:
                logger.error("未获取到股票列表，请先更新股票列表")
                return self.update_stats
            
            self.update_stats['total_stocks'] = len(stocks)
            logger.info(f"待更新股票: {len(stocks)} 只")
            logger.info(f"待更新周期: {self.update_stats['updated_cycles']}")
            
            # 获取配置的线程数
            max_threads = config.scheduler.get('max_download_threads', 2)
            threads = min(threads, max_threads)
            
            # 构建任务列表
            tasks = []
            for _, row in stocks.iterrows():
                code = row['code']
                for cycle in self.update_stats['updated_cycles']:
                    tasks.append((code, cycle))
            
            # 检查是否有中断的任务可以恢复
            start_index = 0
            if resume:
                running_tasks = self.storage.get_running_tasks()
                if not running_tasks.empty:
                    # 找到最近的中断任务
                    latest_task = running_tasks.sort_values('last_update_time').iloc[-1]
                    start_index = latest_task['current_index']
                    self.update_stats['resumed_from'] = start_index
                    logger.info(f"🔄 从断点恢复，跳过前 {start_index} 个任务")
            
            # 创建任务记录
            self.storage.create_task(self.current_task_id, 'update_all', len(tasks))
            self.storage.set_task_status(self.current_task_id, 'running')
            
            # 执行任务（从断点开始）
            success_count = 0
            fail_count = 0
            
            for i in range(start_index, len(tasks)):
                code, cycle = tasks[i]
                
                try:
                    if self.download_quotes(code, cycle):
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.error(f"任务 {i+1}/{len(tasks)} - {code} {cycle} 失败: {str(e)}")
                
                # 更新任务进度（每10个任务更新一次，避免频繁写库）
                if i % 10 == 0 or i == len(tasks) - 1:
                    self.storage.update_task_progress(
                        self.current_task_id,
                        i,
                        code,
                        cycle,
                        success_count,
                        fail_count
                    )
                
                # 更新统计
                self.update_stats['success_count'] = success_count
                self.update_stats['fail_count'] = fail_count
            
            # 标记任务完成
            self.storage.set_task_status(self.current_task_id, 'completed')
            
            # 完成统计
            self.update_stats['end_time'] = datetime.now()
            self.update_stats['fallback_count'] = self.dsm.fallback_count
            duration = (self.update_stats['end_time'] - self.update_stats['start_time']).total_seconds()
            
            logger.info("=" * 60)
            logger.info("全量更新完成")
            logger.info("=" * 60)
            logger.info(f"股票数量: {self.update_stats['total_stocks']}")
            logger.info(f"成功: {self.update_stats['success_count']}")
            logger.info(f"失败: {self.update_stats['fail_count']}")
            logger.info(f"降级次数: {self.update_stats['fallback_count']}")
            if self.update_stats['resumed_from']:
                logger.info(f"从断点恢复: 跳过 {self.update_stats['resumed_from']} 个任务")
            logger.info(f"耗时: {duration:.2f} 秒")
            logger.info("=" * 60)
            
            return self.update_stats
            
        except Exception as e:
            logger.error(f"全量更新失败: {str(e)}")
            if self.current_task_id:
                self.storage.set_task_status(self.current_task_id, 'failed', str(e))
            return self.update_stats
    
    def download_all_with_resume(self, threads: int = 1, cycles: Optional[List[str]] = None) -> dict:
        """
        带断点续传的全量更新（便捷方法）
        
        Args:
            threads: 线程数
            cycles: 指定周期列表
        
        Returns:
            更新统计结果
        """
        return self.download_all(threads=threads, cycles=cycles, resume=True)
    
    def get_task_progress(self, task_id: str = None) -> Optional[Dict[str, Any]]:
        """获取任务进度"""
        if task_id is None:
            task_id = self.current_task_id
        
        if task_id is None:
            return None
        
        return self.storage.get_task_progress(task_id)
    
    def get_running_tasks(self) -> pd.DataFrame:
        """获取所有进行中的任务"""
        return self.storage.get_running_tasks()
    
    def cancel_task(self, task_id: str = None) -> bool:
        """取消任务"""
        if task_id is None:
            task_id = self.current_task_id
        
        if task_id is None:
            return False
        
        return self.storage.set_task_status(task_id, 'failed', '任务已取消')
    
    def cleanup_stale_tasks(self, hours: int = 24) -> int:
        """清理超时任务"""
        return self.storage.cleanup_stale_tasks(hours)
    
    def _process_single_task(self, code: str, cycle: str):
        """处理单个下载任务（带重试机制）"""
        max_retries = config.datasource.get('max_retries', 3)
        retry_delay = config.datasource.get('retry_delay', 1.0)
        
        for attempt in range(max_retries):
            try:
                if self.download_quotes(code, cycle):
                    self.update_stats['success_count'] += 1
                    return
            except Exception as e:
                logger.warning(f"尝试 {attempt + 1}/{max_retries} - {code} {cycle} 失败: {str(e)}")
                time.sleep(retry_delay * (attempt + 1))
        
        logger.error(f"多次尝试失败，跳过 {code} {cycle}")
        self.update_stats['fail_count'] += 1
    
    @cache_decorator('stock_list', ttl=CACHE_CONFIG['stock_list_ttl'])
    def get_stock_list(self) -> pd.DataFrame:
        """获取股票列表"""
        return self.storage.get_stock_list()
    
    @cache_decorator('quotes', ttl=CACHE_CONFIG['quotes_ttl'])
    def get_quotes(
        self,
        code: str,
        cycle: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取行情数据"""
        return self.storage.get_quotes(code, cycle, start_date, end_date)
    
    @cache_decorator('last_date', ttl=CACHE_CONFIG['quotes_ttl'])
    def get_last_date(self, code: str, cycle: str) -> Optional[str]:
        """获取最后日期"""
        return self.storage.get_last_date(code, cycle)
    
    def clear_cache(self, prefix: str = None):
        """清除缓存"""
        self.cache.clear(prefix)
        logger.info(f"缓存已清除: {prefix or '全部'}")
    
    def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        return self.cache.get_stats()
    
    def get_update_report(self) -> dict:
        """获取更新报告"""
        return self.update_stats
    
    def validate_connection(self) -> bool:
        """验证连接状态"""
        try:
            stats = self.storage.get_stats()
        except:
            return False
        return self.dsm.current_source is not None
    
    def get_stats(self) -> dict:
        """获取系统统计信息"""
        return self.storage.get_stats()
    
    def get_current_source(self) -> str:
        """获取当前数据源名称"""
        return self.dsm.current_source_name if self.dsm.current_source else "未连接"
    
    # ==================== 数据完整性巡检 ====================
    
    def inspect_data_integrity(self, cycles: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        巡检数据完整性，找出缺失的数据
        
        Args:
            cycles: 指定周期列表，默认所有周期
        
        Returns:
            巡检结果字典，包含缺失数据统计和详情
        """
        logger.info("=" * 60)
        logger.info("开始数据完整性巡检")
        logger.info("=" * 60)
        
        result = {
            'total_stocks': 0,
            'checked_cycles': cycles or ['daily'],
            'total_missing_dates': 0,
            'stocks_with_missing_data': [],
            'inspection_details': [],
            'start_time': datetime.now(),
            'end_time': None
        }
        
        try:
            # 获取股票列表
            stocks = self.storage.get_stock_list()
            if stocks.empty:
                logger.warning("未获取到股票列表")
                return result
            
            result['total_stocks'] = len(stocks)
            
            # 获取交易日历
            calendar_df = pd.read_sql_query(
                'SELECT cal_date FROM trade_calendar WHERE is_open = 1 ORDER BY cal_date',
                self.storage.conn
            )
            
            if calendar_df.empty:
                logger.warning("未获取到交易日历")
                return result
            
            trade_dates = set(calendar_df['cal_date'].tolist())
            
            # 遍历检查每只股票
            for _, row in stocks.iterrows():
                code = row['code']
                list_date = row.get('list_date', '2000-01-01')
                
                stock_missing = []
                
                for cycle in result['checked_cycles']:
                    # 获取该股票该周期的数据日期
                    quotes_df = self.storage.get_quotes(code, cycle)
                    
                    if quotes_df.empty:
                        # 该股票该周期没有任何数据
                        stock_missing.append({
                            'cycle': cycle,
                            'missing_dates': 'no_data',
                            'count': -1
                        })
                        continue
                    
                    # 找出已有的日期
                    existing_dates = set(quotes_df['trade_date'].tolist())
                    
                    # 计算应该有的日期范围
                    first_date = quotes_df['trade_date'].min()
                    last_date = quotes_df['trade_date'].max()
                    
                    # 找出缺失的日期
                    expected_dates = {d for d in trade_dates if first_date <= d <= last_date}
                    missing_dates = sorted(expected_dates - existing_dates)
                    
                    if missing_dates:
                        stock_missing.append({
                            'cycle': cycle,
                            'missing_dates': missing_dates[:10],  # 只保留前10个
                            'count': len(missing_dates),
                            'first_date': first_date,
                            'last_date': last_date
                        })
                
                if stock_missing:
                    result['stocks_with_missing_data'].append({
                        'code': code,
                        'name': row.get('name', ''),
                        'missing_info': stock_missing
                    })
            
            # 统计总缺失数
            for stock in result['stocks_with_missing_data']:
                for missing in stock['missing_info']:
                    if missing['count'] > 0:
                        result['total_missing_dates'] += missing['count']
            
            result['end_time'] = datetime.now()
            duration = (result['end_time'] - result['start_time']).total_seconds()
            
            logger.info("=" * 60)
            logger.info("数据完整性巡检完成")
            logger.info("=" * 60)
            logger.info(f"检查股票数: {result['total_stocks']}")
            logger.info(f"检查周期: {result['checked_cycles']}")
            logger.info(f"存在缺失数据的股票数: {len(result['stocks_with_missing_data'])}")
            logger.info(f"总缺失日期数: {result['total_missing_dates']}")
            logger.info(f"耗时: {duration:.2f} 秒")
            logger.info("=" * 60)
            
            return result
        
        except Exception as e:
            logger.error(f"数据完整性巡检失败: {str(e)}")
            return result
    
    def repair_missing_data(self, max_stocks: int = 10, cycles: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        修复缺失的数据（自动补全）
        
        Args:
            max_stocks: 最大修复股票数（避免一次性修复过多）
            cycles: 指定周期列表
        
        Returns:
            修复结果统计
        """
        logger.info("=" * 60)
        logger.info("开始修复缺失数据")
        logger.info("=" * 60)
        
        result = {
            'total_repaired': 0,
            'failed_stocks': [],
            'success_stocks': [],
            'start_time': datetime.now(),
            'end_time': None
        }
        
        try:
            # 先执行巡检
            inspection = self.inspect_data_integrity(cycles)
            
            if not inspection['stocks_with_missing_data']:
                logger.info("✅ 没有发现缺失数据")
                result['end_time'] = datetime.now()
                return result
            
            # 限制修复数量
            stocks_to_repair = inspection['stocks_with_missing_data'][:max_stocks]
            logger.info(f"待修复股票: {len(stocks_to_repair)} 只")
            
            for stock_info in stocks_to_repair:
                code = stock_info['code']
                logger.info(f"\n🔧 修复股票: {code}")
                
                success = True
                for missing in stock_info['missing_info']:
                    cycle = missing['cycle']
                    
                    if missing['count'] == -1:
                        # 该周期没有任何数据，从上市日期开始下载
                        logger.info(f"  {cycle}: 无数据，从头开始下载")
                        try:
                            self.download_quotes(code, cycle, start_date=None)
                        except Exception as e:
                            logger.error(f"  {cycle}: 下载失败 - {str(e)}")
                            success = False
                    else:
                        # 有部分缺失，只下载缺失的日期段
                        logger.info(f"  {cycle}: 缺失 {missing['count']} 条数据")
                        try:
                            self.download_quotes(
                                code,
                                cycle,
                                start_date=missing['first_date'],
                                end_date=missing['last_date']
                            )
                        except Exception as e:
                            logger.error(f"  {cycle}: 下载失败 - {str(e)}")
                            success = False
                
                if success:
                    result['success_stocks'].append(code)
                    result['total_repaired'] += 1
                else:
                    result['failed_stocks'].append(code)
            
            result['end_time'] = datetime.now()
            duration = (result['end_time'] - result['start_time']).total_seconds()
            
            logger.info("=" * 60)
            logger.info("数据修复完成")
            logger.info("=" * 60)
            logger.info(f"成功修复: {len(result['success_stocks'])} 只")
            logger.info(f"修复失败: {len(result['failed_stocks'])} 只")
            logger.info(f"耗时: {duration:.2f} 秒")
            logger.info("=" * 60)
            
            return result
        
        except Exception as e:
            logger.error(f"数据修复失败: {str(e)}")
            return result
    
    def get_data_quality_report(self) -> Dict[str, Any]:
        """
        获取数据质量报告
        
        Returns:
            包含完整性、准确性、时效性等指标的报告
        """
        try:
            stats = self.storage.get_stats()
            
            # 检查数据完整性
            inspection = self.inspect_data_integrity(['daily'])
            
            # 计算数据覆盖率
            if stats['stock_count'] > 0:
                coverage_rate = (stats['stock_count'] - len(inspection['stocks_with_missing_data'])) / stats['stock_count'] * 100
            else:
                coverage_rate = 0
            
            # 获取最近更新时间
            cursor = self.storage.conn.execute('SELECT MAX(last_update_time) FROM task_progress WHERE status = %s', ('completed',))
            last_update = cursor.fetchone()[0]
            
            return {
                'stock_count': stats['stock_count'],
                'quotes_count': stats['quotes_count'],
                'cycles': stats['cycles'],
                'calendar_count': stats['calendar_count'],
                'coverage_rate': f"{coverage_rate:.2f}%",
                'stocks_with_missing_data': len(inspection['stocks_with_missing_data']),
                'total_missing_dates': inspection['total_missing_dates'],
                'last_update_time': last_update,
                'data_freshness': self._calculate_data_freshness()
            }
        except Exception as e:
            logger.error(f"生成数据质量报告失败: {str(e)}")
            return {}
    
    def _calculate_data_freshness(self) -> str:
        """计算数据新鲜度"""
        try:
            cursor = self.storage.conn.execute('SELECT MAX(trade_date) FROM stock_quotes')
            last_trade_date = cursor.fetchone()[0]
            
            if not last_trade_date:
                return "未知"
            
            last_date = datetime.strptime(last_trade_date.split(' ')[0], '%Y-%m-%d')
            today = datetime.now()
            delta = (today - last_date).days
            
            if delta == 0:
                return "今日更新"
            elif delta == 1:
                return "昨日更新"
            elif delta <= 7:
                return f"{delta}天前更新"
            elif delta <= 30:
                return f"{delta}天前更新"
            else:
                return f"{delta}天前更新（数据较旧）"
        except Exception:
            return "未知"
    
    # ==================== 技术指标预计算 ====================
    
    def calculate_indicators(self, code: str, cycle: str) -> bool:
        """
        计算并保存单个股票的技术指标
        
        Args:
            code: 股票代码
            cycle: 周期
        
        Returns:
            是否成功
        """
        from clean.processor.technical_indicator import TechnicalIndicator
        
        try:
            # 获取行情数据
            df = self.storage.get_quotes(code, cycle)
            
            if df.empty:
                logger.debug(f"股票 {code} {cycle} 无行情数据，跳过指标计算")
                return False
            
            # 计算技术指标
            df = TechnicalIndicator.calculate_all(df)
            
            # 添加必要字段
            df['code'] = code
            df['cycle'] = cycle
            
            # 保存到数据库
            self.storage.save_indicators(df)
            
            logger.debug(f"✅ 技术指标计算完成: {code} {cycle}")
            return True
        
        except Exception as e:
            logger.error(f"❌ 技术指标计算失败 {code} {cycle}: {str(e)}")
            return False
    
    def calculate_all_indicators(self, cycles: Optional[List[str]] = None) -> dict:
        """
        计算所有股票的技术指标
        
        Args:
            cycles: 指定周期列表，默认 ['daily']
        
        Returns:
            计算统计结果
        """
        logger.info("=" * 60)
        logger.info("开始计算所有技术指标")
        logger.info("=" * 60)
        
        if cycles is None:
            cycles = ['daily']
        
        result = {
            'success_count': 0,
            'fail_count': 0,
            'total_stocks': 0,
            'cycles': cycles,
            'start_time': datetime.now(),
            'end_time': None
        }
        
        try:
            # 获取股票列表
            stocks = self.get_stock_list()
            if stocks.empty:
                logger.warning("未获取到股票列表")
                return result
            
            result['total_stocks'] = len(stocks)
            
            # 遍历计算
            for _, row in stocks.iterrows():
                code = row['code']
                
                for cycle in cycles:
                    if self.calculate_indicators(code, cycle):
                        result['success_count'] += 1
                    else:
                        result['fail_count'] += 1
                
                # 限流控制
                self.rate_limiter.wait()
            
            result['end_time'] = datetime.now()
            duration = (result['end_time'] - result['start_time']).total_seconds()
            
            logger.info("=" * 60)
            logger.info("技术指标计算完成")
            logger.info("=" * 60)
            logger.info(f"股票数量: {result['total_stocks']}")
            logger.info(f"周期: {result['cycles']}")
            logger.info(f"成功: {result['success_count']}")
            logger.info(f"失败: {result['fail_count']}")
            logger.info(f"耗时: {duration:.2f} 秒")
            logger.info("=" * 60)
            
            return result
        
        except Exception as e:
            logger.error(f"技术指标批量计算失败: {str(e)}")
            return result
    
    def update_indicators_incremental(self, cycles: Optional[List[str]] = None) -> dict:
        """
        增量更新技术指标（只更新新增数据的指标）
        
        Args:
            cycles: 指定周期列表
        
        Returns:
            更新统计结果
        """
        logger.info("=" * 60)
        logger.info("开始增量更新技术指标")
        logger.info("=" * 60)
        
        if cycles is None:
            cycles = ['daily']
        
        result = {
            'updated_count': 0,
            'skipped_count': 0,
            'fail_count': 0,
            'cycles': cycles,
            'start_time': datetime.now(),
            'end_time': None
        }
        
        try:
            stocks = self.get_stock_list()
            if stocks.empty:
                logger.warning("未获取到股票列表")
                return result
            
            for _, row in stocks.iterrows():
                code = row['code']
                
                for cycle in cycles:
                    # 获取行情数据最后日期
                    quotes_last_date = self.storage.get_last_date(code, cycle)
                    # 获取指标最后日期
                    indicators_last_date = self.storage.get_indicators_last_date(code, cycle)
                    
                    if not quotes_last_date:
                        result['skipped_count'] += 1
                        continue
                    
                    # 如果指标已最新，跳过
                    if indicators_last_date == quotes_last_date:
                        result['skipped_count'] += 1
                        continue
                    
                    # 需要更新指标
                    if self.calculate_indicators(code, cycle):
                        result['updated_count'] += 1
                    else:
                        result['fail_count'] += 1
                
                self.rate_limiter.wait()
            
            result['end_time'] = datetime.now()
            duration = (result['end_time'] - result['start_time']).total_seconds()
            
            logger.info("=" * 60)
            logger.info("增量更新技术指标完成")
            logger.info("=" * 60)
            logger.info(f"更新: {result['updated_count']}")
            logger.info(f"跳过（已最新）: {result['skipped_count']}")
            logger.info(f"失败: {result['fail_count']}")
            logger.info(f"耗时: {duration:.2f} 秒")
            logger.info("=" * 60)
            
            return result
        
        except Exception as e:
            logger.error(f"增量更新技术指标失败: {str(e)}")
            return result
    
    @cache_decorator('indicators', ttl=CACHE_CONFIG['indicators_ttl'])
    def get_indicators(
        self,
        code: str,
        cycle: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """获取技术指标数据"""
        return self.storage.get_indicators(code, cycle, start_date, end_date)

    # ==================== 快照更新功能 ====================

    def update_snapshot(self) -> bool:
        """
        更新快照数据

        当前仅支持从历史数据生成快照（已移除 Akshare/腾讯/新浪等实时数据源，
        保持数据源仅 Baostock/Tushare/pytdx）。

        Returns:
            是否成功
        """
        logger.info("=" * 60)
        logger.info("开始更新快照（基于历史数据）")
        logger.info("=" * 60)

        try:
            # 确保目录存在
            os.makedirs(SNAPSHOT_PATH, exist_ok=True)
            return self._generate_snapshot_from_history()
        except Exception as e:
            logger.error(f"快照更新失败: {str(e)}")
            return False

    def _generate_snapshot_from_history(self) -> bool:
        """
        从历史数据生成快照（作为备用方案）- 优化版使用批量查询
        
        Returns:
            是否成功
        """
        logger.info("📊 从历史数据生成快照（批量查询模式）...")

        try:
            success_count = 0
            fail_count = 0
            os.makedirs(SNAPSHOT_PATH, exist_ok=True)

            # 批量查询：获取所有股票的最新日线数据
            # 使用窗口函数一次性获取每只股票的最新数据
            query = """
                SELECT q.*, s.name 
                FROM stock_quotes q
                INNER JOIN (
                    SELECT code, MAX(trade_date) as max_date
                    FROM stock_quotes
                    WHERE cycle = 'daily'
                    GROUP BY code
                ) latest ON q.code = latest.code AND q.trade_date = latest.max_date
                LEFT JOIN stock_basic s ON q.code = s.code
                WHERE q.cycle = 'daily'
            """

            try:
                df = pd.read_sql_query(query, self.storage.conn)
            except Exception as e:
                logger.error(f"批量查询失败: {str(e)}")
                return False

            if df.empty:
                logger.warning("⚠️ 没有查询到任何历史数据")
                return False

            logger.info(f"📊 获取到 {len(df)} 条最新行情数据")

            # 批量保存快照
            for _, row in df.iterrows():
                try:
                    code = row['code']
                    name = row.get('name', '')

                    snapshot_data = {
                        'code': code,
                        'name': name,
                        'price': float(row['close']) if pd.notna(row.get('close')) else '',
                        'change': '',
                        'pct_chg': '',
                        'open': float(row['open']) if pd.notna(row.get('open')) else '',
                        'high': float(row['high']) if pd.notna(row.get('high')) else '',
                        'low': float(row['low']) if pd.notna(row.get('low')) else '',
                        'vol': float(row['volume']) if pd.notna(row.get('volume')) else '',
                        'amount': float(row['amount']) if pd.notna(row.get('amount')) else '',
                        'pre_close': '',
                        'turnover_rate': '',
                        'pe': '',
                        'date': str(row['trade_date'])[:10] if pd.notna(row.get('trade_date')) else datetime.now().strftime('%Y-%m-%d'),
                        'time': '15:00:00',
                        'update_time': datetime.now().isoformat(),
                        'source': 'history'
                    }

                    # 保存到文件
                    file_path = os.path.join(SNAPSHOT_PATH, f'{code}.json')
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

                    success_count += 1

                except Exception as e:
                    fail_count += 1
                    logger.debug(f"生成快照失败: {str(e)}")

            logger.info(f"✅ 从历史数据生成快照完成，成功: {success_count}, 失败: {fail_count}")
            return success_count > 0

        except Exception as e:
            logger.error(f"从历史数据生成快照失败: {str(e)}")
            return False

    def is_trading_time(self) -> bool:
        """
        判断当前是否处于交易时段
        
        Returns:
            True if in trading time
        """
        now = datetime.now()
        weekday = now.weekday()  # 0=周一, 4=周五
        
        # 非交易日（周末）
        if weekday >= 5:
            return False
        
        # 上午交易时间: 9:30 - 11:30
        morning_start = now.replace(hour=9, minute=30, second=0)
        morning_end = now.replace(hour=11, minute=30, second=0)
        
        # 下午交易时间: 13:00 - 15:00
        afternoon_start = now.replace(hour=13, minute=0, second=0)
        afternoon_end = now.replace(hour=15, minute=0, second=0)
        
        return (morning_start <= now <= morning_end) or (afternoon_start <= now <= afternoon_end)


# 测试代码
if __name__ == '__main__':
    service = DataService()
    
    if service.connect():
        print("✅ 数据服务连接成功")
        print(f"当前数据源: {service.get_current_source()}")
        
        # 更新交易日历
        print("\n📅 更新交易日历...")
        service.update_trade_calendar()
        
        # 更新股票列表
        print("\n📋 更新股票列表...")
        service.update_stock_basic()
        
        # 获取股票列表
        stocks = service.get_stock_list()
        print(f"\n获取到 {len(stocks)} 只股票")
        print(stocks.head())
        
        # 下载单股票数据测试（带复权）
        print("\n📊 下载测试数据...")
        if not stocks.empty:
            test_code = stocks.iloc[0]['code']
            service.download_quotes(test_code, 'daily', adjust='qfq')
            
            # 查询数据
            data = service.get_quotes(test_code, 'daily')
            print(f"查询到 {len(data)} 条日线数据")
        
        # 获取统计信息
        stats = service.get_stats()
        print(f"\n📈 系统统计: {stats}")
        
        # 关闭服务
        service.disconnect()
        print("\n✅ 数据服务已关闭")
    else:
        print("❌ 数据服务连接失败")

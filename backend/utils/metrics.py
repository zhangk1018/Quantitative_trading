#!/usr/bin/env python3
"""监控指标模块 - 记录任务执行时长、数据处理量、失败率等指标"""
import time
import statistics
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
from utils.logger import setup_logger

logger = setup_logger('metrics')


class TaskMetrics:
    """任务指标收集器 - 记录单个任务的执行指标"""
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.start_time = time.time()
        self.end_time = None
        self.records_processed = 0
        self.records_successful = 0
        self.records_failed = 0
        self.stocks_processed = 0
        self.stocks_failed = 0
        self.retries = 0
        self.errors = []
        self._timers = {}  # 子任务计时器
        self._timer_stack = []  # 计时器栈
    
    def start_timer(self, name: str):
        """开始子任务计时"""
        self._timers[name] = {'start': time.time(), 'end': None, 'count': 0}
        self._timer_stack.append(name)
    
    def end_timer(self, name: Optional[str] = None):
        """结束子任务计时"""
        if name is None:
            if self._timer_stack:
                name = self._timer_stack.pop()
            else:
                return
        
        if name in self._timers:
            self._timers[name]['end'] = time.time()
            self._timers[name]['count'] += 1
    
    def add_record(self, success: bool = True):
        """记录处理记录数"""
        self.records_processed += 1
        if success:
            self.records_successful += 1
        else:
            self.records_failed += 1
    
    def add_stock(self, success: bool = True):
        """记录处理股票数"""
        self.stocks_processed += 1
        if not success:
            self.stocks_failed += 1
    
    def add_retry(self):
        """记录重试次数"""
        self.retries += 1
    
    def add_error(self, error: str, context: Optional[Dict] = None):
        """记录错误信息"""
        self.errors.append({
            'timestamp': datetime.now().isoformat(),
            'error': error,
            'context': context or {}
        })
    
    def finish(self):
        """标记任务完成"""
        self.end_time = time.time()
    
    @property
    def duration(self) -> float:
        """任务持续时间（秒）"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.records_processed == 0:
            return 0.0
        return self.records_successful / self.records_processed * 100
    
    @property
    def stock_success_rate(self) -> float:
        """股票处理成功率"""
        if self.stocks_processed == 0:
            return 0.0
        return (self.stocks_processed - self.stocks_failed) / self.stocks_processed * 100
    
    def get_summary(self) -> Dict[str, Any]:
        """获取任务指标摘要"""
        timers_summary = {}
        for name, timer in self._timers.items():
            if timer['end'] is not None:
                elapsed = timer['end'] - timer['start']
                timers_summary[name] = {
                    'duration': round(elapsed, 2),
                    'count': timer['count']
                }
        
        return {
            'task_name': self.task_name,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            'duration': round(self.duration, 2),
            'records_processed': self.records_processed,
            'records_successful': self.records_successful,
            'records_failed': self.records_failed,
            'records_success_rate': round(self.success_rate, 2),
            'stocks_processed': self.stocks_processed,
            'stocks_failed': self.stocks_failed,
            'stocks_success_rate': round(self.stock_success_rate, 2),
            'retries': self.retries,
            'errors_count': len(self.errors),
            'timers': timers_summary
        }
    
    def print_summary(self):
        """打印任务摘要"""
        summary = self.get_summary()
        
        print(f"\n{'='*60}")
        print(f"任务指标汇总: {self.task_name}")
        print(f"{'='*60}")
        print(f"开始时间: {summary['start_time']}")
        print(f"结束时间: {summary['end_time']}")
        print(f"持续时间: {summary['duration']:.2f} 秒")
        print(f"\n【记录处理】")
        print(f"  处理总数: {summary['records_processed']}")
        print(f"  成功: {summary['records_successful']}")
        print(f"  失败: {summary['records_failed']}")
        print(f"  成功率: {summary['records_success_rate']:.2f}%")
        print(f"\n【股票处理】")
        print(f"  处理总数: {summary['stocks_processed']}")
        print(f"  失败: {summary['stocks_failed']}")
        print(f"  成功率: {summary['stocks_success_rate']:.2f}%")
        print(f"\n【其他】")
        print(f"  重试次数: {summary['retries']}")
        print(f"  错误数量: {summary['errors_count']}")
        
        if summary['timers']:
            print(f"\n【子任务耗时】")
            for name, timer in summary['timers'].items():
                print(f"  {name}: {timer['duration']:.2f}s ({timer['count']}次)")
        
        print(f"{'='*60}")


class GlobalMetrics:
    """全局指标管理器 - 收集所有任务的指标"""
    
    _instance = None
    
    def __init__(self):
        self.tasks: List[TaskMetrics] = []
        self.task_stats: Dict[str, List[float]] = defaultdict(list)
        self.daily_stats: Dict[str, Any] = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_records': 0,
            'total_stocks': 0,
            'total_errors': 0,
            'avg_duration': 0.0
        }
    
    @classmethod
    def get_instance(cls) -> 'GlobalMetrics':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = GlobalMetrics()
        return cls._instance
    
    def create_task_metrics(self, task_name: str) -> TaskMetrics:
        """创建新的任务指标收集器"""
        metrics = TaskMetrics(task_name)
        self.tasks.append(metrics)
        return metrics
    
    def record_task(self, metrics: TaskMetrics):
        """记录任务完成信息"""
        summary = metrics.get_summary()
        task_type = summary['task_name'].split('_')[0]
        self.task_stats[task_type].append(summary['duration'])
        
        # 更新每日统计
        self.daily_stats['total_records'] += summary['records_processed']
        self.daily_stats['total_stocks'] += summary['stocks_processed']
        self.daily_stats['total_errors'] += summary['errors_count']
        
        # 计算平均时长
        if self.tasks:
            total_duration = sum(t.duration for t in self.tasks)
            self.daily_stats['avg_duration'] = total_duration / len(self.tasks)
        
        logger.info(f"任务完成: {summary['task_name']} - "
                   f"时长: {summary['duration']:.2f}s, "
                   f"记录: {summary['records_processed']}, "
                   f"成功率: {summary['records_success_rate']:.2f}%")
    
    def get_global_summary(self) -> Dict[str, Any]:
        """获取全局指标摘要"""
        if not self.tasks:
            return {'message': '暂无任务数据'}
        
        total_duration = sum(t.duration for t in self.tasks)
        total_records = sum(t.records_processed for t in self.tasks)
        total_stocks = sum(t.stocks_processed for t in self.tasks)
        total_errors = sum(len(t.errors) for t in self.tasks)
        total_retries = sum(t.retries for t in self.tasks)
        
        success_rates = [t.success_rate for t in self.tasks if t.records_processed > 0]
        avg_success_rate = statistics.mean(success_rates) if success_rates else 0
        
        task_type_stats = {}
        for task_type, durations in self.task_stats.items():
            if durations:
                task_type_stats[task_type] = {
                    'count': len(durations),
                    'avg_duration': round(statistics.mean(durations), 2),
                    'min_duration': round(min(durations), 2),
                    'max_duration': round(max(durations), 2)
                }
        
        return {
            'total_tasks': len(self.tasks),
            'total_duration': round(total_duration, 2),
            'total_records': total_records,
            'total_stocks': total_stocks,
            'total_errors': total_errors,
            'total_retries': total_retries,
            'avg_success_rate': round(avg_success_rate, 2),
            'task_type_stats': task_type_stats,
            'daily_stats': self.daily_stats
        }
    
    def print_global_summary(self):
        """打印全局指标摘要"""
        summary = self.get_global_summary()
        
        if 'message' in summary:
            print(summary['message'])
            return
        
        print(f"\n{'='*70}")
        print(f"全局指标汇总")
        print(f"{'='*70}")
        print(f"任务总数: {summary['total_tasks']}")
        print(f"总耗时: {summary['total_duration']:.2f} 秒")
        print(f"总处理记录: {summary['total_records']:,}")
        print(f"总处理股票: {summary['total_stocks']:,}")
        print(f"总错误数: {summary['total_errors']:,}")
        print(f"总重试次数: {summary['total_retries']:,}")
        print(f"平均成功率: {summary['avg_success_rate']:.2f}%")
        
        if summary['task_type_stats']:
            print(f"\n【任务类型统计】")
            for task_type, stats in summary['task_type_stats'].items():
                print(f"  {task_type}:")
                print(f"    执行次数: {stats['count']}")
                print(f"    平均耗时: {stats['avg_duration']:.2f}s")
                print(f"    最小耗时: {stats['min_duration']:.2f}s")
                print(f"    最大耗时: {stats['max_duration']:.2f}s")
        
        print(f"\n【每日统计】")
        print(f"  日期: {summary['daily_stats']['date']}")
        print(f"  处理记录: {summary['daily_stats']['total_records']:,}")
        print(f"  处理股票: {summary['daily_stats']['total_stocks']:,}")
        print(f"  错误数: {summary['daily_stats']['total_errors']:,}")
        print(f"  平均时长: {summary['daily_stats']['avg_duration']:.2f}s")
        
        print(f"{'='*70}")
    
    def reset(self):
        """重置所有指标（每日重置）"""
        self.tasks = []
        self.task_stats.clear()
        self.daily_stats = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_records': 0,
            'total_stocks': 0,
            'total_errors': 0,
            'avg_duration': 0.0
        }
        logger.info("全局指标已重置")


# 便捷装饰器
def track_metrics(task_name: str = None):
    """
    装饰器：自动收集函数执行指标
    
    Args:
        task_name: 任务名称，默认使用函数名
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            name = task_name or func.__name__
            metrics = GlobalMetrics.get_instance().create_task_metrics(name)
            
            try:
                result = func(*args, **kwargs)
                
                # 从返回值提取指标
                if isinstance(result, dict):
                    if 'total_records' in result:
                        metrics.records_processed = result.get('total_records', 0)
                        metrics.records_successful = result.get('success', 0) * 100  # 假设成功数
                        metrics.records_failed = result.get('failed', 0) * 100
                    if 'success' in result:
                        metrics.stocks_processed = result.get('success', 0) + result.get('failed', 0)
                        metrics.stocks_failed = result.get('failed', 0)
                
                return result
            except Exception as e:
                metrics.add_error(str(e))
                raise
            finally:
                metrics.finish()
                GlobalMetrics.get_instance().record_task(metrics)
        
        return wrapper
    return decorator


# 上下文管理器
class metrics_context:
    """
    上下文管理器：在代码块中收集指标
    
    Usage:
        with metrics_context('my_task') as metrics:
            # 执行任务
            metrics.add_record(success=True)
            metrics.add_stock(success=True)
    """
    
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.metrics = None
    
    def __enter__(self):
        self.metrics = GlobalMetrics.get_instance().create_task_metrics(self.task_name)
        return self.metrics
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.metrics:
            if exc_type is not None:
                self.metrics.add_error(str(exc_val))
            self.metrics.finish()
            GlobalMetrics.get_instance().record_task(self.metrics)


# 测试代码
if __name__ == '__main__':
    # 测试指标收集
    with metrics_context('测试任务') as metrics:
        metrics.start_timer('数据拉取')
        time.sleep(0.5)
        metrics.end_timer('数据拉取')
        
        metrics.start_timer('数据处理')
        time.sleep(0.3)
        metrics.end_timer('数据处理')
        
        for i in range(100):
            metrics.add_record(success=True)
        for i in range(10):
            metrics.add_stock(success=True)
        
        metrics.add_retry()
    
    # 打印摘要
    GlobalMetrics.get_instance().print_global_summary()
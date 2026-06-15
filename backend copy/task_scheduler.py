#!/usr/bin/env python3
"""定时任务调度器模块 - 包含任务优先级、失败重试、告警策略"""
import time
import os
import shutil
import json
from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from core.service.data_service import DataService
from utils.logger import setup_logger
from utils.config import config
from utils.error_classifier import ErrorClassifier, ErrorType

logger = setup_logger('task_scheduler')


class TaskPriority:
    """任务优先级枚举"""
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class TaskStatus:
    """任务状态枚举"""
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
    RETRYING = 'retrying'
    INTERRUPTED = 'interrupted'


class TaskWithRetry:
    """带重试机制的任务包装器（支持错误分类）"""
    
    def __init__(self, func, max_retries: int = 3, retry_delay: int = 60, priority: str = TaskPriority.MEDIUM):
        self.func = func
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.priority = priority
        self.retry_count = 0
        self.status = TaskStatus.PENDING
        self.last_error = None
        self.error_type = None
    
    def run(self):
        """执行任务（带重试，区分可重试与不可重试错误）"""
        self.status = TaskStatus.RUNNING
        
        while self.retry_count < self.max_retries:
            try:
                self.func()
                self.status = TaskStatus.COMPLETED
                logger.info(f"✅ 任务完成，重试次数: {self.retry_count}")
                return True
            except Exception as e:
                self.retry_count += 1
                self.last_error = str(e)
                
                # 分类错误类型
                self.error_type, _ = ErrorClassifier.classify(e)
                
                # 判断是否可重试
                if not ErrorClassifier.should_retry(e, self.retry_count, self.max_retries):
                    self.status = TaskStatus.FAILED
                    if self.error_type == ErrorType.NON_RETRYABLE:
                        logger.error(f"❌ 任务失败（不可重试错误，跳过重试）: {str(e)}")
                    else:
                        logger.error(f"❌ 任务最终失败（已重试 {self.max_retries} 次）: {str(e)}")
                    return False
                
                # 可重试错误，等待后重试
                self.status = TaskStatus.RETRYING
                delay = ErrorClassifier.get_retry_delay(self.retry_count, self.retry_delay)
                
                logger.warning(f"⚠️ 任务失败（第 {self.retry_count}/{self.max_retries} 次，{self.error_type}）: {str(e)}")
                logger.info(f"等待 {delay} 秒后重试...")
                time.sleep(delay)
        
        self.status = TaskStatus.FAILED
        return False


class TaskScheduler:
    """定时任务调度器 - 支持优先级、重试和告警"""
    
    def __init__(self):
        self.service = DataService()
        self.scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
        self.is_running = False
        
        # 任务统计
        self.metrics = {}
        
        # 任务队列（按优先级）
        self.task_queue = {
            TaskPriority.HIGH: [],
            TaskPriority.MEDIUM: [],
            TaskPriority.LOW: []
        }
        
        # 任务状态记录
        self.task_status = {}
        
        # 告警阈值配置
        self.alert_thresholds = config.alert.get('threshold', {})
    
    def start(self):
        """启动调度器"""
        logger.info("启动定时任务调度器...")
        
        # 添加任务
        self._add_jobs()
        
        # 启动
        self.scheduler.start()
        self.is_running = True
        logger.info("✅ 定时任务调度器已启动")
        
        # 保持运行
        try:
            while True:
                time.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            self.stop()
    
    def stop(self):
        """停止调度器"""
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("✅ 定时任务调度器已停止")
    
    def _add_jobs(self):
        """添加定时任务（按优先级）"""
        # 获取配置的时间
        daily_update_time = config.scheduler.get('daily_update_time', '20:10').split(':')
        closing_time = config.scheduler.get('closing_time', '15:10').split(':')
        daily_list_update_time = config.scheduler.get('daily_stock_list_update_time', '17:30').split(':')
        weekly_maintenance_time = config.scheduler.get('weekly_maintenance_time', '02:00').split(':')
        weekly_maintenance_day = config.scheduler.get('weekly_maintenance_day', 6)
        integrity_check_time = config.scheduler.get('integrity_check_time', '03:00').split(':')

        # 每日股票列表更新（高优先级）
        self.scheduler.add_job(
            self._wrap_with_retry(self.daily_stock_list_job, priority=TaskPriority.HIGH),
            trigger=CronTrigger(hour=int(daily_list_update_time[0]), minute=int(daily_list_update_time[1])),
            id='daily_stock_list',
            name='每日股票列表更新',
            misfire_grace_time=300,
            max_instances=1
        )

        # 收盘作业（高优先级）- 15:10 收盘后下载当日交易数据
        self.scheduler.add_job(
            self._wrap_with_retry(self.closing_job, priority=TaskPriority.HIGH),
            trigger=CronTrigger(hour=int(closing_time[0]), minute=int(closing_time[1]), day_of_week='0-4'),
            id='closing',
            name='收盘作业',
            misfire_grace_time=600,
            max_instances=1
        )

        # 每日行情更新（高优先级）
        self.scheduler.add_job(
            self._wrap_with_retry(self.daily_update_job, priority=TaskPriority.HIGH),
            trigger=CronTrigger(hour=int(daily_update_time[0]), minute=int(daily_update_time[1])),
            id='daily_update',
            name='每日行情更新',
            misfire_grace_time=300,
            max_instances=1
        )
        
        # 每周维护任务（中优先级）
        self.scheduler.add_job(
            self._wrap_with_retry(self.weekly_maintenance_job, priority=TaskPriority.MEDIUM),
            trigger=CronTrigger(day_of_week=weekly_maintenance_day, hour=int(weekly_maintenance_time[0]), minute=int(weekly_maintenance_time[1])),
            id='weekly_maintenance',
            name='每周数据库维护',
            misfire_grace_time=300,
            max_instances=1
        )
        
        # 每日数据完整性检查（低优先级）
        self.scheduler.add_job(
            self._wrap_with_retry(self.daily_integrity_check_job, priority=TaskPriority.LOW),
            trigger=CronTrigger(hour=int(integrity_check_time[0]), minute=int(integrity_check_time[1])),
            id='daily_integrity_check',
            name='每日数据完整性检查',
            misfire_grace_time=600,
            max_instances=1
        )

        # 交易时段快照更新（每5分钟）
        # 上午: 9:30-11:30, 下午: 13:00-15:00
        self.scheduler.add_job(
            self._wrap_with_retry(self.snapshot_update_job, priority=TaskPriority.MEDIUM),
            trigger=CronTrigger(
                minute='*/5',
                hour='9-11,13-14',
                day_of_week='0-4'  # 周一到周五
            ),
            id='snapshot_update',
            name='交易时段快照更新',
            misfire_grace_time=30,
            max_instances=1
        )
    
    def _wrap_with_retry(self, func, priority: str = TaskPriority.MEDIUM):
        """包装任务，添加重试机制"""
        def wrapped():
            task_name = func.__name__
            max_retries = config.scheduler.get('max_retries', 3)
            retry_delay = config.scheduler.get('retry_delay', 60)
            
            task = TaskWithRetry(func, max_retries, retry_delay, priority)
            success = task.run()
            
            # 记录状态
            self.task_status[task_name] = {
                'status': task.status,
                'retry_count': task.retry_count,
                'last_error': task.last_error
            }
            
            # 如果失败，触发告警
            if not success:
                self._trigger_alert(task_name, task.last_error)
            
            return success
        
        return wrapped
    
    def _trigger_alert(self, task_name: str, error_message: str):
        """触发告警"""
        if not config.alert.get('enabled', False):
            return
        
        logger.error(f"🚨 任务失败告警: {task_name} - {error_message}")
        
        # 这里可以扩展：发送邮件、钉钉、企业微信等告警
        # 当前仅记录日志
        alert_record = {
            'timestamp': datetime.now().isoformat(),
            'task_name': task_name,
            'level': 'ERROR',
            'message': error_message,
            'alert_type': 'task_failure'
        }
        
        # 写入告警日志
        alert_dir = 'logs/alerts'
        os.makedirs(alert_dir, exist_ok=True)
        alert_file = os.path.join(alert_dir, f"alerts_{date.today().strftime('%Y%m%d')}.jsonl")
        with open(alert_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(alert_record, ensure_ascii=False) + '\n')
    
    def _check_and_alert(self, task_name: str, metrics: dict):
        """检查指标并触发告警"""
        if not config.alert.get('enabled', False):
            return
        
        fail_rate = self.alert_thresholds.get('fail_rate', 0.1)
        empty_ratio = self.alert_thresholds.get('empty_data_ratio', 0.3)
        latency_threshold = self.alert_thresholds.get('latency_threshold_sec', 300)
        
        alerts = []
        
        # 检查失败率
        if 'stocks_total' in metrics and 'stocks_fail' in metrics:
            if metrics['stocks_total'] > 0:
                rate = metrics['stocks_fail'] / metrics['stocks_total']
                if rate > fail_rate:
                    alerts.append(f"失败率 {rate:.2%} 超过阈值 {fail_rate:.0%}")
        
        # 检查延迟
        if 'latency_sec' in metrics:
            if metrics['latency_sec'] > latency_threshold:
                alerts.append(f"延迟 {metrics['latency_sec']:.2f}秒 超过阈值 {latency_threshold}秒")
        
        if alerts:
            self._trigger_alert(task_name, "; ".join(alerts))
    
    def daily_stock_list_job(self):
        """每日股票列表更新任务"""
        logger.info("=" * 60)
        logger.info("开始每日股票列表更新任务")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        try:
            if self.service.connect():
                self.service.update_stock_basic()
                self.service.disconnect()
                status = "completed"
            else:
                status = "failed"
            
            logger.info("✅ 每日股票列表更新完成")
        
        except Exception as e:
            logger.error(f"每日股票列表更新失败: {str(e)}")
            raise  # 让重试机制处理
        
        finally:
            # 记录指标
            latency = (datetime.now() - start_time).total_seconds()
            metrics = {
                'task': "daily_stock_list",
                'status': status,
                'latency_sec': latency
            }
            self._log_metrics(**metrics)
            self._check_and_alert("daily_stock_list", metrics)
    
    def daily_update_job(self):
        """每日行情更新任务（20:10）- 检查 15:10 收盘作业是否成功"""
        logger.info("=" * 60)
        logger.info("开始每日行情更新任务")
        logger.info("=" * 60)

        start_time = datetime.now()
        today = date.today().strftime('%Y-%m-%d')
        total_stocks = 0
        success_count = 0
        fail_count = 0
        current_idx = 0

        closing_status = self.task_status.get("closing_job", {}).get("status")
        if closing_status == TaskStatus.COMPLETED:
            logger.info(f"⏭️ 收盘作业已于今日完成，跳过每日行情更新")
            logger.info("=" * 60)
            return

        logger.info(f"📋 收盘作业未执行或失败，开始全量更新（start_date 从数据库最后日期+1）")

        try:
            if self.service.connect():
                stocks = self.service.get_stock_list()
                total_stocks = len(stocks)
                success_count = 0
                fail_count = 0

                logger.info(f"📋 开始全量更新日线数据，共 {total_stocks} 只股票")

                for idx, (_, row) in enumerate(stocks.iterrows()):
                    code = row['code']
                    current_idx = idx
                    try:
                        self.service.download_quotes(code, 'daily')
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        logger.warning(f"更新 {code} 失败: {str(e)}")

                    if (idx + 1) % 100 == 0 or idx + 1 == total_stocks:
                        logger.info(f"📊 更新进度: {idx + 1}/{total_stocks}")

                    time.sleep(0.2)  # 避免限流

                self.service.disconnect()
                status = "completed"

                latency = (datetime.now() - start_time).total_seconds()
                metrics = {
                    'task': "daily_update",
                    'stocks_total': len(stocks),
                    'stocks_success': success_count,
                    'stocks_fail': fail_count,
                    'status': status,
                    'latency_sec': latency
                }
                self._log_metrics(**metrics)
                self._check_and_alert("daily_update", metrics)
            else:
                status = "failed"
                self._log_metrics(task="daily_update", status=status, latency_sec=(datetime.now() - start_time).total_seconds())

            logger.info("✅ 每日行情更新完成")

        except KeyboardInterrupt:
            latency = (datetime.now() - start_time).total_seconds()
            logger.warning(f"⚠️ 每日行情更新被用户中断，已处理进度: {current_idx + 1}/{total_stocks}")
            logger.info(f"   成功: {success_count}，失败: {fail_count}，耗时: {latency:.2f} 秒")

            try:
                self.service.disconnect()
            except:
                pass

        except Exception as e:
            logger.error(f"每日行情更新失败: {str(e)}")
            try:
                self.service.disconnect()
            except:
                pass
            raise  # 让重试机制处理
    
    def weekly_maintenance_job(self):
        """每周维护任务：VACUUM + ANALYZE + 自动备份 + 冷数据迁移"""
        logger.info("=" * 60)
        logger.info("开始每周数据库维护任务")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        try:
            # 连接数据库
            if not self.service.storage.connect():
                logger.error("数据库连接失败")
                raise RuntimeError("数据库连接失败")
            
            # 1. VACUUM - 整理数据库文件
            logger.info("🔄 执行 VACUUM")
            self.service.storage.conn.execute("VACUUM")
            self.service.storage.conn.commit()
            
            # 2. ANALYZE - 更新统计信息
            logger.info("🔄 执行 ANALYZE")
            self.service.storage.conn.execute("ANALYZE")
            self.service.storage.conn.commit()
            
            # 3. 冷数据迁移
            logger.info("🔄 执行冷数据迁移")
            self.service.storage.migrate_cold_data()
            
            # 4. 自动备份
            if config.backup.get('enabled', True):
                self._backup_database()
            
            self.service.storage.disconnect()
            
            latency = (datetime.now() - start_time).total_seconds()
            logger.info(f"✅ 每周维护完成，耗时: {latency:.2f} 秒")
            
            # 记录指标
            self._log_metrics(task="weekly_maintenance", status="completed", latency_sec=latency)
            
        except Exception as e:
            logger.error(f"每周维护失败: {str(e)}")
            if self.service.storage.conn:
                self.service.storage.disconnect()
            raise  # 让重试机制处理
    
    def daily_integrity_check_job(self):
        """每日数据完整性检查任务"""
        logger.info("=" * 60)
        logger.info("开始每日数据完整性检查")
        logger.info("=" * 60)
        
        start_time = datetime.now()
        
        try:
            if self.service.connect():
                # 执行完整性检查
                inspection = self.service.inspect_data_integrity(['daily'])
                
                # 检查是否有缺失数据
                if inspection['total_missing_dates'] > 0:
                    logger.warning(f"发现 {inspection['total_missing_dates']} 条缺失数据")
                    
                    # 尝试修复（最多修复5只股票）
                    repair_result = self.service.repair_missing_data(max_stocks=5)
                    logger.info(f"修复完成: {repair_result['total_repaired']} 只股票成功")
                
                self.service.disconnect()
                
                latency = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ 每日数据完整性检查完成，耗时: {latency:.2f} 秒")
                
                # 记录指标
                metrics = {
                    'task': "daily_integrity_check",
                    'missing_stocks': len(inspection['stocks_with_missing_data']),
                    'missing_dates': inspection['total_missing_dates'],
                    'status': "completed",
                    'latency_sec': latency
                }
                self._log_metrics(**metrics)
                
                # 如果缺失数据过多，触发告警
                if inspection['total_missing_dates'] > 100:
                    self._trigger_alert("daily_integrity_check", f"发现 {inspection['total_missing_dates']} 条缺失数据")
            
            else:
                logger.error("连接失败")
                self._log_metrics(task="daily_integrity_check", status="failed", latency_sec=(datetime.now() - start_time).total_seconds())
        
        except Exception as e:
            logger.error(f"每日数据完整性检查失败: {str(e)}")
            if self.service.storage.conn:
                self.service.storage.disconnect()
            raise  # 让重试机制处理
    
    def snapshot_update_job(self):
        """交易时段快照更新任务（每5分钟）"""
        logger.info("=" * 60)
        logger.info("开始快照更新任务")
        logger.info("=" * 60)

        start_time = datetime.now()

        try:
            if self.service.connect():
                # 更新快照
                success = self.service.update_snapshot()

                self.service.disconnect()

                latency = (datetime.now() - start_time).total_seconds()
                status = "completed" if success else "failed"

                logger.info(f"✅ 快照更新任务完成，耗时: {latency:.2f} 秒")

                # 记录指标
                metrics = {
                    'task': "snapshot_update",
                    'status': status,
                    'latency_sec': latency
                }
                self._log_metrics(**metrics)

            else:
                logger.error("连接失败")
                self._log_metrics(task="snapshot_update", status="failed", latency_sec=(datetime.now() - start_time).total_seconds())

        except Exception as e:
            logger.error(f"快照更新任务失败: {str(e)}")
            if self.service.storage.conn:
                self.service.storage.disconnect()
            raise  # 让重试机制处理

    def closing_job(self):
        """收盘作业任务（15:10）- 收盘后下载当日交易数据"""
        logger.info("=" * 60)
        logger.info("开始收盘作业任务")
        logger.info("=" * 60)

        start_time = datetime.now()
        today = date.today().strftime('%Y-%m-%d')
        total_stocks = 0
        success_count = 0
        fail_count = 0
        current_idx = 0

        try:
            if self.service.connect():
                stocks = self.service.get_stock_list()
                total_stocks = len(stocks)
                success_count = 0
                fail_count = 0

                logger.info(f"📋 开始下载 {today} 日线数据，共 {total_stocks} 只股票")

                for idx, (_, row) in enumerate(stocks.iterrows()):
                    code = row['code']
                    current_idx = idx
                    try:
                        self.service.download_quotes(code, 'daily', start_date=today, end_date=today)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        logger.warning(f"下载 {code} 日线数据失败: {str(e)}")

                    if (idx + 1) % 100 == 0 or idx + 1 == total_stocks:
                        logger.info(f"📊 下载进度: {idx + 1}/{total_stocks}")

                    time.sleep(0.2)

                self.service.disconnect()

                latency = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ 收盘作业完成，耗时: {latency:.2f} 秒，成功: {success_count}，失败: {fail_count}")

                self.task_status["closing_job"] = {
                    'status': TaskStatus.COMPLETED,
                    'date': today,
                    'stocks_success': success_count,
                    'stocks_fail': fail_count,
                    'latency_sec': latency
                }

                metrics = {
                    'task': "closing",
                    'date': today,
                    'stocks_success': success_count,
                    'stocks_fail': fail_count,
                    'status': "completed",
                    'latency_sec': latency
                }
                self._log_metrics(**metrics)

            else:
                logger.error("收盘作业失败：数据库连接失败")
                self.task_status["closing_job"] = {
                    'status': TaskStatus.FAILED,
                    'date': today,
                    'error': '数据库连接失败'
                }
                self._log_metrics(task="closing", status="failed", latency_sec=(datetime.now() - start_time).total_seconds())

        except KeyboardInterrupt:
            latency = (datetime.now() - start_time).total_seconds()
            logger.warning(f"⚠️ 收盘作业被用户中断，已处理进度: {current_idx + 1}/{total_stocks}")
            logger.info(f"   成功: {success_count}，失败: {fail_count}，耗时: {latency:.2f} 秒")

            self.task_status["closing_job"] = {
                'status': TaskStatus.INTERRUPTED,
                'date': today,
                'stocks_success': success_count,
                'stocks_fail': fail_count,
                'progress': f"{current_idx + 1}/{total_stocks}",
                'latency_sec': latency
            }

            try:
                self.service.disconnect()
            except:
                pass

        except Exception as e:
            logger.error(f"收盘作业失败: {str(e)}")
            self.task_status["closing_job"] = {
                'status': TaskStatus.FAILED,
                'date': today,
                'error': str(e)
            }
            try:
                self.service.disconnect()
            except:
                pass
            raise

    def _backup_database(self):
        """备份数据库"""
        backup_dir = config.backup.get('backup_dir', 'data/backups')
        max_backups = config.backup.get('max_backups', 30)
        db_path = config.storage.get('db_path', 'data/stock_data.db')
        
        # 确保备份目录存在
        os.makedirs(backup_dir, exist_ok=True)
        
        # 创建备份文件名
        backup_path = os.path.join(backup_dir, f"stock_data_{date.today().strftime('%Y%m%d')}.db")
        
        # 复制文件
        shutil.copy2(db_path, backup_path)
        logger.info(f"📦 数据库已备份至 {backup_path}")
        
        # 清理旧备份
        self._cleanup_old_backups(backup_dir, max_backups)
    
    def _cleanup_old_backups(self, backup_dir: str, max_backups: int):
        """清理旧备份文件"""
        try:
            # 获取所有备份文件并按修改时间排序
            backup_files = sorted(
                [f for f in os.listdir(backup_dir) if f.startswith('stock_data_') and f.endswith('.db')],
                key=lambda x: os.path.getmtime(os.path.join(backup_dir, x))
            )
            
            # 删除多余的备份
            while len(backup_files) > max_backups:
                old_file = backup_files.pop(0)
                old_path = os.path.join(backup_dir, old_file)
                os.remove(old_path)
                logger.debug(f"🗑️ 删除旧备份: {old_file}")
        
        except Exception as e:
            logger.warning(f"清理旧备份失败: {str(e)}")
    
    def _log_metrics(self, **kwargs):
        """记录指标到JSONL文件"""
        metrics_dir = 'logs'
        os.makedirs(metrics_dir, exist_ok=True)
        
        # 构建指标记录
        record = {
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        # 写入JSONL文件
        log_file = os.path.join(metrics_dir, f"metrics_{date.today().strftime('%Y%m%d')}.jsonl")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        
        logger.debug(f"📊 指标已记录: {record}")
    
    def manual_update(self, cycles: list = None, priority: str = TaskPriority.MEDIUM, stock_filter: list = None):
        """手动触发更新（支持优先级和股票筛选）

        Args:
            cycles: 数据周期列表，如 ['daily', 'min5']
            priority: 任务优先级
            stock_filter: 股票代码筛选列表，如 ['sh.60%', 'sz.00%', 'sz.30%'] 表示沪深主板和创业板
                         - sh.60% : 上海主板
                         - sz.00% : 深圳主板
                         - sz.30% : 创业板（科创板 sh.68% 会被排除）
        """
        import pandas as pd

        logger.info("=" * 60)
        logger.info(f"开始手动更新（优先级: {priority}）")
        if stock_filter:
            logger.info(f"股票筛选: {stock_filter}")
        logger.info("=" * 60)

        start_time = datetime.now()

        # 检查是否有高优先级任务正在运行
        if priority == TaskPriority.LOW:
            running_tasks = self.service.get_running_tasks()
            if not running_tasks.empty:
                logger.warning("⚠️ 有高优先级任务正在运行，跳过低优先级手动更新")
                return

        try:
            if self.service.connect():
                # 更新股票列表
                logger.info("🔄 更新股票列表")
                self.service.update_stock_basic()

                # 获取股票列表并应用筛选
                stocks = self.service.get_stock_list()

                if stock_filter:
                    # 应用股票筛选
                    mask = pd.Series([False] * len(stocks), index=stocks.index)
                    for pattern in stock_filter:
                        pattern = pattern.replace('%', '')
                        mask |= stocks['code'].str.startswith(pattern)
                    stocks = stocks[mask]
                    logger.info(f"📊 筛选后股票数量: {len(stocks)}")

                logger.info(f"📊 待更新股票数量: {len(stocks)}")

                # 更新行情数据
                if cycles:
                    for cycle in cycles:
                        logger.info(f"🔄 更新 {cycle} 数据")
                        for _, row in stocks.iterrows():
                            code = row['code']
                            self.service.download_quotes(code, cycle)
                            time.sleep(0.2)
                else:
                    # 默认更新日线
                    logger.info("🔄 更新日线数据")
                    for idx, (_, row) in enumerate(stocks.iterrows(), 1):
                        code = row['code']
                        self.service.download_quotes(code, 'daily')
                        if idx % 100 == 0:
                            logger.info(f"📊 更新进度: {idx}/{len(stocks)}")
                        time.sleep(0.2)

                self.service.disconnect()

                latency = (datetime.now() - start_time).total_seconds()
                logger.info(f"✅ 手动更新完成，耗时: {latency:.2f} 秒")

                # 记录指标
                self._log_metrics(task="manual_update", status="completed", latency_sec=latency)

            else:
                logger.error("连接失败")
                self._log_metrics(task="manual_update", status="failed", latency_sec=(datetime.now() - start_time).total_seconds())

        except Exception as e:
            logger.error(f"手动更新失败: {str(e)}")
            self._log_metrics(task="manual_update", status="failed", latency_sec=(datetime.now() - start_time).total_seconds())
            if self.service.storage.conn:
                self.service.disconnect()
    
    def get_task_status(self, task_name: str = None):
        """获取任务状态"""
        if task_name:
            return self.task_status.get(task_name)
        return self.task_status
    
    def cancel_task(self, task_id: str):
        """取消任务"""
        try:
            self.scheduler.remove_job(task_id)
            logger.info(f"✅ 已取消任务: {task_id}")
            return True
        except Exception as e:
            logger.error(f"取消任务失败: {str(e)}")
            return False


# 测试函数
if __name__ == '__main__':
    scheduler = TaskScheduler()
    # 测试手动更新
    scheduler.manual_update(cycles=['daily'], priority=TaskPriority.MEDIUM)
    print("测试完成")

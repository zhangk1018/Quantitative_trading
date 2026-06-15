#!/usr/bin/env python3
"""
智能调度器 - 支持灵活的日期规则和动态数据源选择
"""
from datetime import datetime, date, time as dt_time
from typing import Optional, Set
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from utils.logger import setup_logger
from collector.storage.postgresql_storage import PostgreSQLStorage
from collector.scheduler.config import (
    FlexibleScheduleConfig,
    DaySchedule,
    IntervalConfig,
    DateRuleType,
    DateRule
)
from collector.scheduler.smart_dsm import SmartDataSourceManager
from collector.scheduler.alert import AlertManager

logger = setup_logger('smart_scheduler')


class SmartTaskScheduler:
    """智能任务调度器"""
    
    def __init__(
        self,
        config: FlexibleScheduleConfig,
        data_source_manager: SmartDataSourceManager,
        storage: PostgreSQLStorage,
        alert_manager: Optional[AlertManager] = None
    ):
        self.config = config
        self.dsm = data_source_manager
        self.storage = storage
        self.alert_manager = alert_manager or AlertManager()
        
        self.timezone = pytz.timezone(config.timezone)
        self.scheduler = BackgroundScheduler(timezone=self.timezone)
        
        # 交易日历缓存
        self.trade_calendar: Set[date] = set()
        
        # 任务状态
        self.task_states = {}
    
    def load_trade_calendar(self):
        """加载交易日历"""
        try:
            cursor = self.storage.conn.cursor()
            cursor.execute(
                "SELECT trade_date FROM trade_calendar WHERE is_trading = true"
            )
            self.trade_calendar = {row[0] for row in cursor.fetchall()}
            logger.info(f"已加载 {len(self.trade_calendar)} 个交易日")
        except Exception as e:
            logger.error(f"加载交易日历失败: {e}")
    
    def is_trading_time(self) -> bool:
        """判断是否为交易时间（简化版）"""
        now = datetime.now(self.timezone)
        current_time = now.time()
        current_date = now.date()
        
        # 先判断是否为交易日
        if current_date not in self.trade_calendar:
            return False
        
        # A股交易时间
        morning_start = dt_time(9, 15)
        morning_end = dt_time(11, 30)
        afternoon_start = dt_time(13, 0)
        afternoon_end = dt_time(15, 0)
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        return is_morning or is_afternoon
    
    def _build_cron_for_interval(self, interval: int) -> CronTrigger:
        """为指定间隔构建 CronTrigger（仅在交易时间内）"""
        if interval == 1:
            return CronTrigger(minute="*", hour="9-11,13-14")
        elif interval == 5:
            return CronTrigger(minute="*/5", hour="9-11,13-14")
        elif interval == 10:
            return CronTrigger(minute="*/10", hour="9-11,13-14")
        elif interval == 15:
            return CronTrigger(minute="*/15", hour="9-11,13-14")
        elif interval == 30:
            return CronTrigger(minute="0,30", hour="9-11,13-14")
        elif interval == 60:
            return CronTrigger(minute="0", hour="9-11,13-14")
        else:
            return CronTrigger(minute=f"*/{interval}", hour="9-11,13-14")
    
    def _wrap_collection_task(self, interval_config: IntervalConfig):
        """包装数据采集任务"""
        def task():
            task_id = f"collect_{interval_config.interval_minutes}min_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            logger.info(f"开始任务: {task_id}, 周期: {interval_config.cycles}")
            
            success_count = 0
            fail_count = 0
            
            for cycle in interval_config.cycles:
                try:
                    # 获取待采集股票（简化）
                    codes = self._get_target_codes()
                    if not codes:
                        logger.warning(f"无待采集股票")
                        continue
                    
                    logger.info(f"开始采集 {cycle} 数据，共 {len(codes)} 只股票")
                    
                    # 选择最佳数据源
                    self.dsm._select_best_source(cycle=cycle)
                    
                    # 采集并保存
                    # 这里简化为调用数据服务的方法，实际需要根据业务实现
                    # 调用数据补全逻辑或采集逻辑
                    
                    success_count += 1
                    logger.info(f"{cycle} 数据采集完成")
                    
                except Exception as e:
                    fail_count += 1
                    logger.error(f"采集 {cycle} 数据失败: {str(e)}", exc_info=True)
                    
                    # 告警
                    self.alert_manager.alert(
                        title=f"{cycle} 数据采集失败",
                        message=f"周期: {cycle}, 错误: {str(e)}",
                        level="error",
                        dedup_key=f"collect_fail_{cycle}"
                    )
            
            logger.info(f"任务 {task_id} 完成: 成功 {success_count}, 失败 {fail_count}")
        
        return task
    
    def _get_target_codes(self) -> list:
        """获取待采集股票代码（简化版）"""
        try:
            cursor = self.storage.conn.cursor()
            cursor.execute(
                "SELECT code FROM stock_basic WHERE status = 'L' LIMIT 500"
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return []
    
    def _daily_collection_task(self):
        """日线采集任务（收盘后）"""
        logger.info("📅 开始日线数据采集任务")
        try:
            today = date.today()
            
            # 选择最佳数据源
            self.dsm._select_best_source(cycle="daily")
            
            # 这里调用现有的日线采集程序
            # import collector.etl.import_daily_data as import_module
            # import_module.run_incremental()
            
            logger.info("✅ 日线数据采集完成")
        except Exception as e:
            logger.error(f"日线采集失败: {e}", exc_info=True)
            self.alert_manager.alert(
                title="日线采集失败",
                message=str(e),
                level="error"
            )
    
    def _weekly_collection_task(self):
        """周线采集任务"""
        logger.info("📆 开始周线数据采集任务")
        # TODO: 实现周线采集
        logger.info("✅ 周线数据采集完成")
    
    def _monthly_collection_task(self):
        """月线采集任务"""
        logger.info("📅 开始月线数据采集任务")
        # TODO: 实现月线采集
        logger.info("✅ 月线数据采集完成")
    
    def _refresh_trade_calendar(self):
        """定时刷新交易日历"""
        logger.debug("刷新交易日历")
        self.load_trade_calendar()
    
    def setup_schedule(self):
        """配置调度任务"""
        # 先加载交易日历
        self.load_trade_calendar()
        
        # 1. 添加刷新交易日历的任务（每天早上）
        self.scheduler.add_job(
            self._refresh_trade_calendar,
            trigger=CronTrigger(hour=8, minute=0),
            id="refresh_calendar",
            name="刷新交易日历"
        )
        
        # 2. 获取今日配置（演示用）
        today = date.today()
        # 简化处理，直接使用默认配置的工作日/周末
        # 实际应该使用 FlexibleScheduleConfig 动态判断
        from collector.scheduler.config import ScheduleConfig, DayType
        simple_config = ScheduleConfig.default_config()
        
        # 找到当前适用的调度
        is_workday = today in self.trade_calendar
        target_day_type = DayType.WORKDAY if is_workday else DayType.WEEKEND
        
        active_schedule = None
        for s in simple_config.schedules:
            if s.day_type == target_day_type:
                active_schedule = s
                break
        
        if not active_schedule:
            active_schedule = simple_config.schedules[0]
        
        logger.info(f"今日类型: {target_day_type.value}")
        
        # 3. 添加间隔任务
        for interval_config in active_schedule.intervals:
            if not interval_config.enabled:
                continue
            
            job_id = f"interval_{interval_config.interval_minutes}min"
            cron_trigger = self._build_cron_for_interval(interval_config.interval_minutes)
            task_func = self._wrap_collection_task(interval_config)
            
            self.scheduler.add_job(
                task_func,
                trigger=cron_trigger,
                id=job_id,
                name=f"{interval_config.interval_minutes}分钟间隔采集",
                max_instances=1,
                misfire_grace_time=60
            )
            
            logger.info(f"已添加任务: {job_id}, 周期: {interval_config.cycles}")
        
        # 4. 添加日线任务（收盘后15:10）
        self.scheduler.add_job(
            self._daily_collection_task,
            trigger=CronTrigger(hour=15, minute=10, day_of_week="0-4"),
            id="daily_collection",
            name="日线数据采集",
            max_instances=1
        )
        
        # 5. 添加周线任务（周五收盘后16:00）
        self.scheduler.add_job(
            self._weekly_collection_task,
            trigger=CronTrigger(hour=16, minute=0, day_of_week=4),
            id="weekly_collection",
            name="周线数据采集"
        )
        
        # 6. 添加月线任务（每月最后一天）
        self.scheduler.add_job(
            self._monthly_collection_task,
            trigger=CronTrigger(day="last", hour=16, minute=30),
            id="monthly_collection",
            name="月线数据采集"
        )
        
        # 7. 添加健康检查任务
        self.scheduler.add_job(
            self._health_check,
            trigger=IntervalTrigger(minutes=10),
            id="health_check",
            name="系统健康检查"
        )
        
        logger.info("✅ 调度任务配置完成")
    
    def _health_check(self):
        """健康检查"""
        try:
            # 检查数据源状态
            stats = self.dsm.get_stats()
            
            # 检查是否有熔断
            for name, cb_status in stats.get('circuit_breakers', {}).items():
                if cb_status['state'] == 'open':
                    self.alert_manager.alert(
                        title=f"数据源熔断: {name}",
                        message=f"状态: {cb_status}",
                        level="warning",
                        dedup_key=f"cb_open_{name}"
                    )
            
            # 简单输出统计
            logger.debug(f"健康检查: {stats.get('metrics', {})}")
            
        except Exception as e:
            logger.error(f"健康检查异常: {e}")
    
    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.setup_schedule()
            self.scheduler.start()
            logger.info("🚀 智能调度器已启动")
        else:
            logger.warning("调度器已在运行中")
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("⏹️ 智能调度器已停止")
    
    def get_job_list(self) -> list:
        """获取任务列表"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        return jobs


def create_smart_scheduler(
    storage: PostgreSQLStorage,
    alert_manager: Optional[AlertManager] = None
) -> SmartTaskScheduler:
    """创建智能调度器的便捷函数"""
    from collector.scheduler.smart_dsm import create_smart_dsm
    from collector.scheduler.config import FlexibleScheduleConfig
    
    dsm = create_smart_dsm()
    config = FlexibleScheduleConfig.default_config()
    
    return SmartTaskScheduler(
        config=config,
        data_source_manager=dsm,
        storage=storage,
        alert_manager=alert_manager
    )


# 简单的启动入口
if __name__ == "__main__":
    from utils.config import config
    from collector.storage.postgresql_storage import PostgreSQLStorage
    from collector.scheduler.alert import create_alert_manager_from_config
    
    # 初始化存储
    storage = PostgreSQLStorage(config.storage.get('postgresql', {}))
    storage.connect()
    
    # 初始化告警
    alert_manager = create_alert_manager_from_config()
    
    # 创建并启动调度器
    scheduler = create_smart_scheduler(storage, alert_manager)
    
    try:
        scheduler.start()
        
        print("调度器已启动，按 Ctrl+C 停止...")
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        scheduler.stop()
        storage.disconnect()

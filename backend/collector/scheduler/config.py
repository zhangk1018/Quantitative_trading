#!/usr/bin/env python3
"""
调度配置 - 灵活的日期规则和调度配置
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Dict, Optional, Callable
from utils.logger import setup_logger

logger = setup_logger('scheduler_config')


class DayType(Enum):
    """日期类型"""
    WORKDAY = "workday"   # 工作日
    WEEKEND = "weekend"   # 周末/节假日
    ALL = "all"           # 所有日期


class ScheduleStrategy(Enum):
    """调度策略"""
    SEQUENTIAL = "sequential"    # 按顺序执行
    PARALLEL = "parallel"        # 并行执行
    PRIORITY = "priority"       # 优先级执行


class DateRuleType(Enum):
    """日期规则类型"""
    WORKDAY = "workday"           # 交易日
    WEEKEND = "weekend"           # 周末（非交易日）
    HOLIDAY = "holiday"           # 节假日（含调休）
    CUSTOM = "custom"             # 自定义日期范围


@dataclass
class IntervalConfig:
    """间隔配置"""
    interval_minutes: int        # 间隔分钟数
    cycles: List[str]            # 采集的周期：min5, min15, min30, min60, daily, weekly, monthly
    enabled: bool = True
    priority: int = 0


@dataclass
class DaySchedule:
    """某类日期的调度配置"""
    day_type: DayType
    intervals: List[IntervalConfig]
    strategy: ScheduleStrategy = ScheduleStrategy.SEQUENTIAL


@dataclass
class DateRule:
    """日期规则"""
    rule_type: DateRuleType
    name: str
    # 自定义日期范围（仅 CUSTOM 类型需要）
    custom_dates: Optional[List[date]] = None
    # 自定义日期匹配函数（高级用法）
    custom_matcher: Optional[Callable[[date], bool]] = None
    
    def matches(self, d: date, trade_calendar: set) -> bool:
        """判断日期是否匹配此规则"""
        if self.rule_type == DateRuleType.WORKDAY:
            return d in trade_calendar
        elif self.rule_type == DateRuleType.WEEKEND:
            return d.weekday() >= 5 and d not in trade_calendar
        elif self.rule_type == DateRuleType.HOLIDAY:
            return d not in trade_calendar and self._is_holiday(d)
        elif self.rule_type == DateRuleType.CUSTOM:
            if self.custom_matcher:
                return self.custom_matcher(d)
            return d in (self.custom_dates or [])
        return False
    
    def _is_holiday(self, d: date) -> bool:
        """判断是否为节假日（可从外部配置加载）"""
        # TODO: 这里可以接入法定节假日数据
        return False


@dataclass
class ScheduleConfig:
    """简单调度配置（兼容旧代码）"""
    schedules: List[DaySchedule]
    timezone: str = "Asia/Shanghai"
    enable_concurrent: bool = False
    max_concurrent_tasks: int = 3
    
    @classmethod
    def default_config(cls) -> 'ScheduleConfig':
        """默认配置：工作日5/15/30分钟，周末10/15分钟"""
        return cls(
            schedules=[
                DaySchedule(
                    day_type=DayType.WORKDAY,
                    intervals=[
                        IntervalConfig(interval_minutes=5, cycles=['min5'], priority=3),
                        IntervalConfig(interval_minutes=15, cycles=['min15'], priority=2),
                        IntervalConfig(interval_minutes=30, cycles=['min30', 'min60'], priority=1),
                    ]
                ),
                DaySchedule(
                    day_type=DayType.WEEKEND,
                    intervals=[
                        IntervalConfig(interval_minutes=10, cycles=['min10'], priority=2),
                        IntervalConfig(interval_minutes=15, cycles=['min15'], priority=1),
                    ]
                ),
            ]
        )


@dataclass
class FlexibleScheduleConfig:
    """灵活调度配置（支持自定义日期规则）"""
    # 按优先级排序的日期规则（第一个匹配的生效）
    date_rules: List[DateRule]
    # 每个日期规则对应的调度
    schedules_by_rule: Dict[str, DaySchedule]
    timezone: str = "Asia/Shanghai"
    enable_concurrent: bool = False
    max_concurrent_tasks: int = 3
    
    @classmethod
    def default_config(cls) -> 'FlexibleScheduleConfig':
        """默认配置"""
        workday_rule = DateRule(rule_type=DateRuleType.WORKDAY, name="工作日")
        weekend_rule = DateRule(rule_type=DateRuleType.WEEKEND, name="周末")
        holiday_rule = DateRule(rule_type=DateRuleType.HOLIDAY, name="节假日")
        
        return cls(
            date_rules=[workday_rule, holiday_rule, weekend_rule],  # 优先级顺序
            schedules_by_rule={
                "工作日": DaySchedule(
                    day_type=DayType.WORKDAY,
                    intervals=[
                        IntervalConfig(interval_minutes=5, cycles=['min5'], priority=3),
                        IntervalConfig(interval_minutes=15, cycles=['min15'], priority=2),
                        IntervalConfig(interval_minutes=30, cycles=['min30', 'min60'], priority=1),
                    ]
                ),
                "周末": DaySchedule(
                    day_type=DayType.WEEKEND,
                    intervals=[
                        IntervalConfig(interval_minutes=10, cycles=['min10'], priority=2),
                        IntervalConfig(interval_minutes=15, cycles=['min15'], priority=1),
                    ]
                ),
                "节假日": DaySchedule(
                    day_type=DayType.WEEKEND,  # 节假日用周末配置
                    intervals=[
                        IntervalConfig(interval_minutes=30, cycles=['min30'], priority=1),
                    ]
                ),
            }
        )
    
    def get_active_schedule(self, d: date, trade_calendar: set) -> DaySchedule:
        """获取指定日期的生效调度配置"""
        for rule in self.date_rules:
            if rule.matches(d, trade_calendar):
                if rule.name in self.schedules_by_rule:
                    logger.debug(f"日期 {d} 匹配规则: {rule.name}")
                    return self.schedules_by_rule[rule.name]
        
        # 没有匹配到，返回第一个配置
        if self.schedules_by_rule:
            first_rule_name = next(iter(self.schedules_by_rule.keys()))
            logger.warning(f"日期 {d} 未匹配任何规则，使用默认: {first_rule_name}")
            return self.schedules_by_rule[first_rule_name]
        
        # 都没有，返回空
        return DaySchedule(day_type=DayType.ALL, intervals=[])

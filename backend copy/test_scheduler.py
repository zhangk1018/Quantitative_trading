#!/usr/bin/env python3
"""
测试智能调度模块
"""
import sys
import os

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
from utils.config import config
from collector.storage.postgresql_storage import PostgreSQLStorage
from collector.scheduler import (
    FlexibleScheduleConfig,
    DateRule,
    DateRuleType,
    DaySchedule,
    DayType,
    IntervalConfig,
    CircuitBreakerConfig,
    CircuitBreaker,
    AlertManager,
    ConsoleChannel,
    SmartDataSourceManager,
    create_smart_dsm,
    create_alert_manager_from_config
)

logger = setup_logger('test_scheduler')


def test_config():
    """测试配置模块"""
    print("\n" + "=" * 60)
    print("测试配置模块")
    print("=" * 60)
    
    config_obj = FlexibleScheduleConfig.default_config()
    
    # 打印配置
    for rule in config_obj.date_rules:
        print(f"\n规则: {rule.name} ({rule.rule_type.value})")
        if rule.name in config_obj.schedules_by_rule:
            schedule = config_obj.schedules_by_rule[rule.name]
            print(f"  天数类型: {schedule.day_type.value}")
            for interval in schedule.intervals:
                print(f"    间隔: {interval.interval_minutes}分钟, 周期: {interval.cycles}")
    
    print("\n✅ 配置模块测试完成")
    return True


def test_circuit_breaker():
    """测试熔断器"""
    print("\n" + "=" * 60)
    print("测试熔断器")
    print("=" * 60)
    
    cb_config = CircuitBreakerConfig(
        failure_threshold=3,
        break_duration=10,
        half_open_max_requests=2,
        recovery_threshold=0.5
    )
    
    cb = CircuitBreaker(cb_config, "test_source")
    
    # 测试正常请求
    print(f"\n状态: {cb.state}")
    for i in range(2):
        print(f"请求 {i+1}: 允许={cb.allow_request()}")
        cb.record_success()
        print(f"  → 记录成功, 状态={cb.state}")
    
    # 测试失败熔断
    print(f"\n状态: {cb.state}")
    for i in range(5):
        print(f"请求 {i+1}: 允许={cb.allow_request()}")
        if i < 3:
            cb.record_failure()
            print(f"  → 记录失败, 状态={cb.state}")
    
    print(f"\n状态: {cb.state}")
    print(f"允许请求: {cb.allow_request()}")
    print(f"熔断器状态: {cb.get_status()}")
    
    print("\n✅ 熔断器测试完成")
    return True


def test_alert():
    """测试告警"""
    print("\n" + "=" * 60)
    print("测试告警")
    print("=" * 60)
    
    manager = AlertManager()
    manager.add_channel(ConsoleChannel())
    
    manager.alert(
        title="测试告警",
        message="这是一条测试告警信息",
        level="info"
    )
    
    manager.alert(
        title="警告测试",
        message="这是一条警告信息",
        level="warning"
    )
    
    manager.alert(
        title="错误测试",
        message="这是一条错误信息",
        level="error"
    )
    
    print("\n✅ 告警测试完成")
    return True


def test_smart_dsm():
    """测试智能数据源管理器"""
    print("\n" + "=" * 60)
    print("测试智能数据源管理器")
    print("=" * 60)
    
    dsm = create_smart_dsm()
    
    # 初始状态
    stats = dsm.get_stats()
    print(f"\n当前数据源: {stats.get('current_source')}")
    print(f"健康状态: {stats.get('health_status')}")
    
    if 'metrics' in stats:
        print(f"\n数据源指标:")
        for name, m in stats['metrics'].items():
            print(f"  {name}: {m}")
    
    # 尝试获取数据
    print(f"\n尝试获取 K线数据...")
    try:
        df = dsm.get_kline("000001.SZ", cycle="daily", start_date="2024-01-01", end_date="2024-01-10")
        
        if df is not None and not df.empty:
            print(f"✅ 成功获取 {len(df)} 条记录")
        else:
            print(f"⚠️ 获取到空数据")
            
    except Exception as e:
        print(f"❌ 获取失败: {e}")
    
    # 再次获取统计
    print(f"\n更新后的指标:")
    stats = dsm.get_stats()
    if 'metrics' in stats:
        for name, m in stats['metrics'].items():
            print(f"  {name}: {m}")
    
    # 清理
    dsm.close()
    
    print("\n✅ 智能数据源管理器测试完成")
    return True


def main():
    """主测试函数"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 18 + "智能调度模块测试" + " " * 20 + "║")
    print("╚" + "═" * 58 + "╝")
    
    results = []
    
    try:
        results.append(("配置模块", test_config()))
    except Exception as e:
        logger.error(f"配置模块测试异常: {e}", exc_info=True)
        results.append(("配置模块", False))
    
    try:
        results.append(("熔断器", test_circuit_breaker()))
    except Exception as e:
        logger.error(f"熔断器测试异常: {e}", exc_info=True)
        results.append(("熔断器", False))
    
    try:
        results.append(("告警", test_alert()))
    except Exception as e:
        logger.error(f"告警测试异常: {e}", exc_info=True)
        results.append(("告警", False))
    
    try:
        results.append(("智能数据源管理器", test_smart_dsm()))
    except Exception as e:
        logger.error(f"智能数据源管理器测试异常: {e}", exc_info=True)
        results.append(("智能数据源管理器", False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for name, ok in results:
        status = "✅  通过" if ok else "❌  失败"
        print(f"  {name:20s} - {status}")
        if ok:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
数据质量监控告警系统

监控指标：
1. 数据完整性：检查各表数据量是否正常
2. 缺失值比例：监控关键字段缺失情况
3. 数据新鲜度：检查最近更新时间
4. 异常值检测：检测价格、成交量等异常
"""
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import time
from datetime import datetime, timedelta
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('data_quality_monitor')


def get_quality_metrics():
    """获取数据质量指标"""
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'user': db_config.get('user', 'postgres'),
        'password': db_config.get('password', '')
    })

    if not storage.connect():
        logger.error("❌ 数据库连接失败")
        return None

    metrics = {}

    try:
        # 1. stock_quotes 表监控
        cursor = storage.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total_rows, 
                   MAX(trade_date) as latest_date,
                   MIN(trade_date) as earliest_date
            FROM stock_quotes
            WHERE cycle = '1d'
        """)
        result = cursor.fetchone()
        if result:
            latest_date = result[1]
            data_freshness = None
            if latest_date:
                # 修复：统一转换为 datetime 类型进行计算
                latest_datetime = datetime.combine(latest_date, datetime.min.time())
                data_freshness = (datetime.now() - latest_datetime).days
            
            metrics['stock_quotes'] = {
                'total_rows': result[0],
                'latest_date': result[1],
                'earliest_date': result[2],
                'data_freshness': data_freshness
            }

        # 2. stock_indicators 表监控
        cursor.execute("""
            SELECT COUNT(*) as total_rows,
                   SUM(CASE WHEN ma5 IS NULL THEN 1 ELSE 0 END) as ma5_nulls,
                   SUM(CASE WHEN macd IS NULL THEN 1 ELSE 0 END) as macd_nulls,
                   MAX(trade_date) as latest_date
            FROM stock_indicators
        """)
        result = cursor.fetchone()
        if result:
            metrics['stock_indicators'] = {
                'total_rows': result[0],
                'ma5_nulls': result[1],
                'macd_nulls': result[2],
                'latest_date': result[3],
                'null_rate': (result[1] + result[2]) / max(result[0], 1) * 100
            }

        # 3. stock_basic 表监控
        cursor.execute("""
            SELECT COUNT(*) as total_rows,
                   SUM(CASE WHEN list_date IS NULL THEN 1 ELSE 0 END) as null_list_date
            FROM stock_basic
        """)
        result = cursor.fetchone()
        if result:
            metrics['stock_basic'] = {
                'total_stocks': result[0],
                'null_list_date': result[1]
            }

        # 4. trade_signals 表监控
        cursor.execute("""
            SELECT COUNT(*) as total_signals,
                   MAX(trade_date) as latest_signal_date
            FROM trade_signals
        """)
        result = cursor.fetchone()
        if result:
            metrics['trade_signals'] = {
                'total_signals': result[0],
                'latest_signal_date': result[1]
            }

        # 5. stock_adj_factor 表监控
        cursor.execute("""
            SELECT COUNT(*) as total_records,
                   MAX(trade_date) as latest_date
            FROM stock_adj_factor
        """)
        result = cursor.fetchone()
        if result:
            metrics['stock_adj_factor'] = {
                'total_records': result[0],
                'latest_date': result[1]
            }

        cursor.close()

    except Exception as e:
        logger.error(f"❌ 获取质量指标失败: {e}")
        return None

    return metrics


def check_alerts(metrics):
    """检查告警条件"""
    alerts = []

    # 数据新鲜度告警（超过3天未更新）
    if metrics.get('stock_quotes', {}).get('data_freshness') and \
       metrics['stock_quotes']['data_freshness'] > 3:
        alerts.append({
            'level': 'CRITICAL',
            'message': f"K线数据过时，最新日期: {metrics['stock_quotes']['latest_date']}，已{metrics['stock_quotes']['data_freshness']}天未更新"
        })

    # 缺失值告警
    if metrics.get('stock_indicators', {}).get('null_rate') and \
       metrics['stock_indicators']['null_rate'] > 5:
        alerts.append({
            'level': 'WARNING',
            'message': f"技术指标缺失率过高: {metrics['stock_indicators']['null_rate']:.2f}%"
        })

    # 数据量异常告警
    if metrics.get('stock_basic', {}).get('total_stocks') and \
       metrics['stock_basic']['total_stocks'] < 4000:
        alerts.append({
            'level': 'WARNING',
            'message': f"股票数量异常: {metrics['stock_basic']['total_stocks']} 只（预期>4000）"
        })

    # 信号数量告警
    if metrics.get('trade_signals', {}).get('total_signals') and \
       metrics['trade_signals']['total_signals'] < 1000:
        alerts.append({
            'level': 'WARNING',
            'message': f"交易信号数量不足: {metrics['trade_signals']['total_signals']} 条（预期>1000）"
        })

    return alerts


def generate_report(metrics, alerts):
    """生成数据质量报告"""
    report = []
    report.append("=" * 70)
    report.append(f"📊 数据质量监控报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 70)

    # 数据概览
    report.append("\n📈 数据概览:")
    report.append(f"  📦 stock_quotes: {metrics.get('stock_quotes', {}).get('total_rows', 0):,} 条日线数据")
    report.append(f"  📊 stock_indicators: {metrics.get('stock_indicators', {}).get('total_rows', 0):,} 条技术指标")
    report.append(f"  📋 stock_basic: {metrics.get('stock_basic', {}).get('total_stocks', 0):,} 只股票")
    report.append(f"  🚦 trade_signals: {metrics.get('trade_signals', {}).get('total_signals', 0):,} 条信号")
    report.append(f"  🔄 stock_adj_factor: {metrics.get('stock_adj_factor', {}).get('total_records', 0):,} 条复权因子")

    # 数据新鲜度
    report.append("\n⏱️ 数据新鲜度:")
    quotes_freshness = metrics.get('stock_quotes', {}).get('data_freshness')
    if quotes_freshness is not None:
        status = "✅ 正常" if quotes_freshness <= 1 else "⚠️ 稍旧" if quotes_freshness <= 3 else "❌ 过时"
        report.append(f"  K线数据: {status}（{quotes_freshness} 天前）")

    # 告警信息
    if alerts:
        report.append("\n🔔 告警列表:")
        for alert in alerts:
            icon = "🔴" if alert['level'] == 'CRITICAL' else "🟡"
            report.append(f"  {icon} [{alert['level']}] {alert['message']}")
    else:
        report.append("\n✅ 所有指标正常，无告警")

    report.append("\n" + "=" * 70)
    return "\n".join(report)


def main():
    """主函数"""
    logger.info("=" * 70)
    logger.info("开始数据质量监控...")
    logger.info("=" * 70)

    # 获取质量指标
    metrics = get_quality_metrics()
    if not metrics:
        logger.error("❌ 无法获取质量指标")
        return

    # 检查告警
    alerts = check_alerts(metrics)

    # 生成报告
    report = generate_report(metrics, alerts)
    print(report)
    logger.info(report)

    # 如果有告警，写入告警日志
    if alerts:
        alert_log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'logs', 'monitoring', 'alerts.log'
        )
        os.makedirs(os.path.dirname(alert_log_path), exist_ok=True)
        
        with open(alert_log_path, 'a') as f:
            f.write(f"[{datetime.now().isoformat()}] ALERTS:\n")
            for alert in alerts:
                f.write(f"  [{alert['level']}] {alert['message']}\n")
            f.write("\n")

        logger.warning(f"⚠️ 发现 {len(alerts)} 个告警，已写入告警日志")


if __name__ == '__main__':
    main()

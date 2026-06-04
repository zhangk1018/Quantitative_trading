#!/usr/bin/env python3
"""
清理旧数据脚本

功能：
- 删除格式不统一的旧日线数据
- 删除旧分钟线数据
- 支持按时间范围清理（保留近N天数据或指定日期之前）
- 支持 Dry Run 模式预览删除数量
- 分批删除避免锁表

用法：
    python scripts/clean_old_data.py --daily --days 90   # 清理90天前的日线数据
    python scripts/clean_old_data.py --minute --days 90   # 清理90天前的分钟线数据
    python scripts/clean_old_data.py --all --days 90     # 清理所有90天前的数据
    python scripts/clean_old_data.py --daily --force     # 无确认直接清理所有日线数据
    python scripts/clean_old_data.py --daily --before-date 2024-01-01  # 清理指定日期前的数据
    python scripts/clean_old_data.py --daily --days 90 --batch-size 5000  # 指定分批大小
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import argparse
import re
from datetime import datetime, timedelta, timezone
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('clean_data')

# 时区定义
CST = timezone(timedelta(hours=8), 'CST')  # UTC+8


def validate_date(date_str: str) -> bool:
    """校验日期格式"""
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', date_str))


def _batch_delete(cursor, table: str, condition: str, param: tuple, batch_size: int = 1000) -> int:
    """PostgreSQL 兼容的分批删除（使用 ctid 子查询，带 ORDER BY 保证稳定扫描）
    
    Args:
        cursor: 数据库游标
        table: 表名
        condition: WHERE 条件
        param: 条件参数
        batch_size: 每批次删除条数，默认1000条，大数据量表建议增大
        
    Returns:
        总共删除的记录数
    """
    total_deleted = 0
    
    # 根据表大小动态调整批次大小
    cursor.execute(f"SELECT reltuples::bigint FROM pg_class WHERE relname = %s", (table,))
    row = cursor.fetchone()
    estimated_rows = row[0] if row else 0
    
    # 大数据量表使用更大的批次
    if estimated_rows > 1000000:
        effective_batch_size = min(batch_size, 10000)
    elif estimated_rows > 100000:
        effective_batch_size = min(batch_size, 5000)
    else:
        effective_batch_size = batch_size
    
    logger.debug(f"表 {table} 估计行数: {estimated_rows}, 使用批次大小: {effective_batch_size}")
    
    while True:
        # 添加 ORDER BY ctid 保证稳定扫描，避免数据不一致
        cursor.execute(f"""
            DELETE FROM {table}
            WHERE ctid IN (
                SELECT ctid FROM {table}
                WHERE {condition}
                ORDER BY ctid LIMIT %s
            )
        """, param + (effective_batch_size,))
        deleted = cursor.rowcount
        if deleted == 0:
            break
        total_deleted += deleted
        cursor.connection.commit()
        logger.debug(f"已删除 {total_deleted} 条...")
    
    return total_deleted


def _clean_data(storage: PostgreSQLStorage, table_name: str, table_desc: str, 
               days: int = None, before_date: str = None, force: bool = False, 
               dry_run: bool = False, batch_size: int = 1000, 
               extra_condition: str = None) -> int:
    """通用数据清理函数
    
    Args:
        storage: 数据库存储对象
        table_name: 表名
        table_desc: 表描述（用于日志输出）
        days: 保留近N天的数据
        before_date: 删除此日期之前的数据
        force: 是否跳过确认直接删除
        dry_run: 是否模拟运行
        batch_size: 分批大小
        extra_condition: 额外的WHERE条件（如 "cycle = '1d'"）
    
    Returns:
        删除的记录数
    """
    cursor = storage.conn.cursor()
    
    # 构建完整条件
    conditions = []
    params = []
    
    if before_date:
        if not validate_date(before_date):
            logger.error(f"❌ 无效日期格式: {before_date}，应为 YYYY-MM-DD")
            return 0
        conditions.append("trade_date < %s")
        params.append(before_date)
        cutoff_display = before_date
    elif days:
        # 使用 UTC+8 时区计算截止日期
        cutoff_date = (datetime.now(CST) - timedelta(days=days)).strftime('%Y-%m-%d')
        conditions.append("trade_date < %s")
        params.append(cutoff_date)
        cutoff_display = cutoff_date
    else:
        cutoff_display = "所有"
    
    if extra_condition:
        conditions.append(extra_condition)
    
    # 构建WHERE子句
    if conditions:
        where_clause = " AND ".join(conditions)
    else:
        where_clause = "1=1"
    
    # 构建计数查询
    count_sql = f"SELECT COUNT(*) FROM {table_name}"
    if conditions:
        count_sql += f" WHERE {where_clause}"
    
    cursor.execute(count_sql, tuple(params))
    count = cursor.fetchone()[0]
    
    # 处理确认逻辑（非强制模式且非时间范围清理时需要确认）
    need_confirm = not force and not days and not before_date
    if need_confirm:
        logger.warning(f"⚠️ 即将删除 {table_desc} 所有 {count} 条数据")
        # 非交互环境检测
        try:
            import sys
            if not sys.stdin.isatty():
                logger.error("❌ 非交互环境下需要使用 --force 参数跳过确认")
                return 0
            
            confirm = input("确认删除？(yes/no): ")
            if confirm.lower() != 'yes':
                logger.info("⏭️ 取消删除")
                return 0
        except Exception:
            logger.error("❌ 无法获取用户输入，非交互环境请使用 --force 参数")
            return 0
    
    if dry_run:
        logger.info(f"[Dry Run] 🗑️ 将要清理{table_desc}（{cutoff_display}之前）: {count} 条")
        return count
    
    # 执行实际删除
    deleted = _batch_delete(cursor, table_name, where_clause, tuple(params), batch_size)
    logger.info(f"✅ 清理{table_desc}（{cutoff_display}之前）完成: {deleted} 条")
    
    return deleted


def clean_daily_data(storage: PostgreSQLStorage, days: int = None, before_date: str = None, 
                     force: bool = False, dry_run: bool = False, batch_size: int = 1000) -> int:
    """清理日线数据 - 支持分批删除避免锁表"""
    return _clean_data(storage, 'stock_quotes', '日线数据', days, before_date, 
                       force, dry_run, batch_size, extra_condition="cycle = '1d'")


def clean_minute_data(storage: PostgreSQLStorage, days: int = None, before_date: str = None, 
                      force: bool = False, dry_run: bool = False, batch_size: int = 1000) -> int:
    """清理分钟线数据 - 支持分批删除避免锁表"""
    return _clean_data(storage, 'stock_quotes_minute', '分钟线数据', days, before_date, 
                       force, dry_run, batch_size)


def main():
    parser = argparse.ArgumentParser(description='清理旧数据脚本')
    parser.add_argument('--daily', action='store_true', help='清理日线数据')
    parser.add_argument('--minute', action='store_true', help='清理分钟线数据')
    parser.add_argument('--all', action='store_true', help='清理所有数据')
    parser.add_argument('--days', type=int, help='保留近N天的数据，删除此前的数据')
    parser.add_argument('--before-date', type=str, help='删除此日期之前的数据（YYYY-MM-DD）')
    parser.add_argument('--force', action='store_true', help='跳过确认直接删除（危险）')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际删除数据')
    parser.add_argument('--batch-size', type=int, default=1000, 
                        help='分批删除大小（默认1000，大数据量表可增大）')

    args = parser.parse_args()

    if args.days and args.before_date:
        logger.error("❌ 不能同时指定 --days 和 --before-date")
        return

    if not args.force and not args.days and not args.before_date and not args.dry_run:
        logger.info("⚠️ 建议使用 --days 或 --before-date 指定清理范围，或使用 --force 跳过确认")

    if args.dry_run:
        logger.info("ℹ️ Dry Run 模式：仅显示将要删除的数据量，不实际删除")

    # 验证批次大小
    if args.batch_size <= 0:
        logger.error("❌ 批次大小必须大于0")
        return

    storage_config = config.storage.get('postgresql', {})
    storage = PostgreSQLStorage(storage_config)
    storage.connect()

    try:
        if args.all:
            clean_daily_data(storage, args.days, args.before_date, args.force, args.dry_run, args.batch_size)
            clean_minute_data(storage, args.days, args.before_date, args.force, args.dry_run, args.batch_size)
            if args.dry_run:
                logger.info("✅ [Dry Run] 所有数据清理预览完成")
            else:
                logger.info("✅ 所有数据清理完成")
        elif args.daily:
            clean_daily_data(storage, args.days, args.before_date, args.force, args.dry_run, args.batch_size)
            if args.dry_run:
                logger.info("✅ [Dry Run] 日线数据清理预览完成")
            else:
                logger.info("✅ 日线数据清理完成")
        elif args.minute:
            clean_minute_data(storage, args.days, args.before_date, args.force, args.dry_run, args.batch_size)
            if args.dry_run:
                logger.info("✅ [Dry Run] 分钟线数据清理预览完成")
            else:
                logger.info("✅ 分钟线数据清理完成")
        else:
            logger.info("⚠️ 请指定要清理的数据类型：--daily、--minute 或 --all")
    finally:
        storage.disconnect()


if __name__ == '__main__':
    main()

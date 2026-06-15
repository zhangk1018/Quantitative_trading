#!/usr/bin/env python3
"""
分区自动维护调度脚本
用途：定期检查并创建分区，支持 cron 调度

使用方式：
1. 手动执行：python scripts/partition_scheduler.py
2. cron 调度（每月1日凌晨1点）：
   0 1 1 * * /path/to/python /path/to/scripts/partition_scheduler.py
"""

import argparse
import logging
from datetime import datetime

# 添加项目路径
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class PartitionScheduler:
    def __init__(self, dry_run: bool = False):
        storage_config = config.storage.get('postgresql', {})
        self.storage = PostgreSQLStorage(storage_config)
        self.storage.connect()
        self.dry_run = dry_run

    def _add_months(self, dt, months):
        """计算 months 个月后的日期（始终返回该月第1天）"""
        year = dt.year + (dt.month + months - 1) // 12
        month = (dt.month + months - 1) % 12 + 1
        return dt.replace(year=year, month=month, day=1)

    def _partition_exists(self, partition_name: str, parent_table: str) -> bool:
        """检查分区是否存在且属于指定父表"""
        cursor = self.storage.conn.cursor()
        cursor.execute("""
            SELECT 1 FROM pg_class c
            JOIN pg_inherits i ON c.oid = i.inhrelid
            JOIN pg_class p ON i.inhparent = p.oid
            WHERE c.relname = %s AND p.relname = %s
        """, (partition_name, parent_table))
        return cursor.fetchone() is not None

    def _call_procedure(self, proc_name: str, params: tuple, success_msg: str, fail_msg: str) -> bool:
        """调用存储过程的通用方法（封装事务处理）"""
        if self.dry_run:
            logger.info(f"🔍 [DRY-RUN] 将执行: CALL {proc_name}({params})")
            return True

        try:
            cursor = self.storage.conn.cursor()
            # 动态生成占位符，适配不同参数数量的存储过程
            placeholders = ', '.join(['%s'] * len(params))
            cursor.execute(f"CALL {proc_name}({placeholders})", params)
            self.storage.conn.commit()
            logger.info(f"✅ {success_msg}")
            return True
        except Exception as e:
            self.storage.conn.rollback()
            logger.warning(f"⚠️ {fail_msg}: {e}")
            return False

    def create_next_month_partitions(self):
        """创建下月的分钟线表分区"""
        today = datetime.now()
        next_month = self._add_months(today, 1)
        year = next_month.year
        month = next_month.month

        table_name = 'stock_quotes_minute'
        partition_name = f'{table_name}_{year}{month:02d}'

        if self._partition_exists(partition_name, table_name):
            logger.debug(f"分区 {partition_name} 已存在，跳过")
            return

        self._call_procedure(
            'add_month_partition',
            (table_name, year, month),
            f"成功为 {table_name} 创建 {year}-{month:02d} 分区",
            f"创建分区失败 {table_name} {year}-{month:02d}"
        )

    def create_next_year_partitions(self):
        """创建下一年的日线表分区"""
        today = datetime.now()
        next_year = today.year + 1

        for table_name in ['stock_quotes', 'stock_indicators']:
            partition_name = f'{table_name}_{next_year}'

            if self._partition_exists(partition_name, table_name):
                logger.debug(f"分区 {partition_name} 已存在，跳过")
                continue

            self._call_procedure(
                'add_year_partition',
                (table_name, next_year),
                f"成功为 {table_name} 创建 {next_year} 年度分区",
                f"创建分区失败 {table_name} {next_year}"
            )

    def check_and_create_missing_partitions(self):
        """检查并创建缺失的分区"""
        today = datetime.now()

        # 检查本月和下月分钟线分区
        for offset in [0, 1]:
            check_date = self._add_months(today, offset)
            year = check_date.year
            month = check_date.month
            table_name = 'stock_quotes_minute'
            partition_name = f'{table_name}_{year}{month:02d}'

            if not self._partition_exists(partition_name, table_name):
                logger.info(f"🔍 发现缺失分区 {partition_name}，正在创建...")
                self._call_procedure(
                    'add_month_partition',
                    (table_name, year, month),
                    f"已创建缺失分区 {partition_name}",
                    f"创建分区失败 {partition_name}"
                )

        # 检查本年和下年日线分区
        for year in [today.year, today.year + 1]:
            for table_name in ['stock_quotes', 'stock_indicators']:
                partition_name = f'{table_name}_{year}'

                if not self._partition_exists(partition_name, table_name):
                    logger.info(f"🔍 发现缺失分区 {partition_name}，正在创建...")
                    self._call_procedure(
                        'add_year_partition',
                        (table_name, year),
                        f"已创建缺失分区 {partition_name}",
                        f"创建分区失败 {partition_name}"
                    )

    def run(self, mode='auto'):
        """运行调度任务"""
        mode_messages = {
            'auto': '自动模式（创建下月/下年分区）',
            'check': '检查模式（检查并修复缺失分区）',
            'full': '完整模式（检查 + 创建）'
        }
        logger.info(f"🚀 开始执行分区维护调度... [{mode_messages.get(mode, mode)}]")

        if mode == 'auto':
            self.create_next_month_partitions()
            self.create_next_year_partitions()
        elif mode == 'check':
            self.check_and_create_missing_partitions()
        elif mode == 'full':
            self.check_and_create_missing_partitions()
            self.create_next_month_partitions()
            self.create_next_year_partitions()

        logger.info("✅ 分区维护调度执行完成")

    def close(self):
        """关闭连接"""
        if self.storage and self.storage.conn:
            self.storage.conn.close()


def main():
    parser = argparse.ArgumentParser(description='分区自动维护调度脚本')
    parser.add_argument(
        '--mode',
        choices=['auto', 'check', 'full'],
        default='auto',
        help='运行模式：auto=创建下月/下年分区（默认），check=检查缺失分区，full=完整维护'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='模拟执行，打印将要执行的操作而不实际调用存储过程'
    )
    args = parser.parse_args()

    scheduler = PartitionScheduler(dry_run=args.dry_run)
    try:
        scheduler.run(mode=args.mode)
    finally:
        scheduler.close()


if __name__ == '__main__':
    main()
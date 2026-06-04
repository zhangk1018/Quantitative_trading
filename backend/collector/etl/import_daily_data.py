#!/usr/bin/env python3
"""
日线数据导入脚本

功能：
- 从数据源（baostock）拉取日线K线
- 写入 stock_quotes 表
- 利用 task_progress 记录状态
- 支持全量导入和增量导入

用法：
    python scripts/import_daily_data.py                    # 全量导入所有标的
    python scripts/import_daily_data.py --code 000001      # 单股票导入
    python scripts/import_daily_data.py --start 2025-01-01 # 指定起始日期
    python scripts/import_daily_data.py --end 2026-05-30   # 指定结束日期
    python scripts/import_daily_data.py --incremental      # 增量导入

设计说明：
    baostock 库本身不是线程安全的，且 baostock.py 内部已有 _run_baostock_with_timeout
    做超时控制。因此本脚本不再额外使用 threading，避免双重线程嵌套导致：
    - 孤儿线程堆积（超时后线程仍活着但被遗弃）
    - 非线程安全的 bs 模块被并发调用 → 进程崩溃
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List

from collector.datasource.baostock import BaostockDataSource
from clean.processor.base_importer import BaseDataImporter
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('daily_import')

# 请求间隔配置（符合各数据源频率限制）
# BaoStock: ≤20次/分钟，建议0.1秒以上/次
REQUEST_INTERVAL = 0.2  # 请求间隔（秒），保守设置避免触发限流


class DailyDataImporter(BaseDataImporter):
    """日线数据导入器 - 继承 BaseDataImporter"""

    def __init__(self):
        super().__init__()
        self.datasource = BaostockDataSource()
        self._interrupted = False

    def close(self):
        """关闭连接（与 disconnect 等效）"""
        self.disconnect()

    def import_stock_data(self, code: str, start_date: str, end_date: str) -> int:
        """导入单只股票日线数据（超时由 baostock.py 内部控制）"""
        try:
            df = self.retry_on_network_error(
                self.datasource.get_kline,
                code, cycle='daily', start_date=start_date, end_date=end_date,
                max_retries=3, initial_delay=5, max_delay=30
            )
            if df is None or df.empty:
                return 0

            df = self._process_kline_data(df)
            if df is None or df.empty:
                return 0

            df['code'] = self._format_code(code)
            df['cycle'] = '1d'
            df['adjust_type'] = 'qfq'
            df = df[['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close', 'volume', 'amount', 'adjust_type']]

            count = self.storage.save_quotes(df)
            logger.debug(f"导入 {code}: {count} 条记录")
            return count

        except (ConnectionError, OSError) as e:
            logger.error(f"❌ {code} 网络异常，跳过该股票: {e}")
            return 0
        except Exception as e:
            logger.error(f"❌ 导入 {code} 失败: {e}")
            return 0

    def _process_kline_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理K线数据（子类可重写）"""
        df['open'] = pd.to_numeric(df['open'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').astype('Int64')
        df['volume'] = df['volume'].where(df['volume'].notna() & (df['volume'] != ''), None)
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            df = df[df[col] > 0]

        df = df[df['volume'].notna() & (df['volume'] > 0)]
        df['pct_change'] = df['close'].pct_change() * 100
        df = df.dropna(subset=['open', 'close'])

        return df

    def full_import(self, codes: List[str], start_date: str = None, end_date: str = None):
        """全量导入（支持断点续传）"""
        total_stocks = len(codes)
        success_count = 0
        fail_count = 0
        skip_count = 0
        total_records = 0
        self._interrupted = False

        # 使用上下文管理器确保 cursor 正确关闭
        with self.storage.conn.cursor() as cursor:
            # 优化：预批量查询所有股票的最后交易日（避免逐只检查）
            if not start_date:
                logger.info("⏩ 全量模式：预批量查询已有数据的股票...")
                last_date_cache = self.batch_get_last_trade_date(codes)
                logger.info("✅ 预查询完成")
            else:
                # 如果指定了日期范围，预查询该日期范围内已有的数据
                logger.info("⏩ 日期范围模式：预批量查询该日期范围内已有的数据...")
                last_date_cache = {}
                # 批量查询指定日期范围内是否已有数据
                # 构建代码映射：原始代码 -> 纯数字代码（用于查询）
                code_mapping = {}
                numeric_codes = []
                for code in codes:
                    numeric_code = code.replace('SZ.', '').replace('sz.', '').replace('SH.', '').replace('sh.', '')
                    code_mapping[code] = numeric_code
                    numeric_codes.append(numeric_code)
                    
                placeholders = ','.join(['%s'] * len(numeric_codes))
                sql = f"""
                    SELECT code, COUNT(*) 
                    FROM stock_quotes
                    WHERE code IN ({placeholders}) AND cycle = '1d' AND trade_date >= %s AND trade_date <= %s
                    GROUP BY code
                """
                
                with self.storage.conn.cursor() as cursor_check:
                    cursor_check.execute(sql, tuple(numeric_codes) + (start_date, end_date if end_date else start_date))
                    rows = cursor_check.fetchall()
                    
                    # 构建数值代码到是否有数据的映射
                    existing_codes = {row[0]: True for row in rows}
                    
                    # 将结果映射回原始代码格式
                    for original_code, numeric_code in code_mapping.items():
                        if numeric_code in existing_codes:
                            last_date_cache[original_code] = start_date  # 标记该日期已有数据
        
        logger.info("✅ 预查询完成")

        for i, code in enumerate(codes, 1):
            if self._interrupted:
                logger.info(f"检测到中断信号，停止导入")
                break

            # 每 100 只股票检查一次数据库连接
            if i % 100 == 0:
                self._ensure_db_connected()

            formatted_code = self._format_code(code)
            if not formatted_code:
                logger.warning(f"[{i}/{total_stocks}] {code} 格式无效，跳过")
                continue

            # 使用预查询缓存（用原始代码查询，因为缓存的 key 是原始格式）
            last_date = last_date_cache.get(code)
            if last_date:
                skip_count += 1
                if skip_count <= 5 or skip_count % 500 == 0:
                    logger.info(f"[{i}/{total_stocks}] {code} 已有数据({last_date})，跳过")
                continue

            logger.info(f"[{i}/{total_stocks}] 正在导入 {code}")

            if start_date:
                current_start = start_date
            else:
                with self.storage.conn.cursor() as cursor:
                    cursor.execute("SELECT list_date FROM stock_basic WHERE code = %s", (formatted_code,))
                    result = cursor.fetchone()
                    current_start = result[0] if result else '2000-01-01'

            count = self.import_stock_data(code, current_start, end_date)

            if count > 0:
                success_count += 1
                total_records += count
            else:
                fail_count += 1

            progress = int((i / total_stocks) * 100)
            self.update_task_progress('running', progress, f"已完成 {i}/{total_stocks} 只股票")

            # 使用配置的请求间隔，避免触发频率限制
            time.sleep(REQUEST_INTERVAL)

        logger.info(f"全量导入完成: 成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}, 总记录 {total_records}")
        self.update_task_progress('completed', 100,
                                 f"全量导入完成: 成功 {success_count}, 失败 {fail_count}, 跳过 {skip_count}, 总记录 {total_records}")

    def incremental_import(self):
        """增量导入"""
        codes = self.get_stock_list()
        today = datetime.now().strftime('%Y-%m-%d')

        total_stocks = len(codes)
        success_count = 0
        fail_count = 0
        total_records = 0

        # 优化：预批量查询所有股票的最后交易日
        logger.info("⏩ 增量模式：预批量查询所有股票的最后交易日...")
        last_date_cache = self.batch_get_last_trade_date(codes)
        logger.info("✅ 预查询完成")

        for i, code in enumerate(codes, 1):
            # 检查股票是否已退市
            with self.storage.conn.cursor() as cursor:
                cursor.execute("SELECT delist_date FROM stock_basic WHERE code = %s", (code,))
                result = cursor.fetchone()
                if result and result[0]:
                    logger.debug(f"{code} 已退市（退市日期: {result[0]}），跳过")
                    continue
            
            last_date = last_date_cache.get(code)

            if last_date:
                start_date = (datetime.strptime(last_date, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
                if start_date > today:
                    logger.debug(f"{code} 数据已是最新，跳过")
                    continue
            else:
                with self.storage.conn.cursor() as cursor:
                    cursor.execute("SELECT list_date FROM stock_basic WHERE code = %s", (code,))
                    result = cursor.fetchone()
                    start_date = result[0] if result else '2000-01-01'

            logger.info(f"[{i}/{total_stocks}] 增量导入 {code}，从 {start_date} 开始")

            count = self.import_stock_data(code, start_date, today)

            if count > 0:
                success_count += 1
                total_records += count
            else:
                fail_count += 1

            progress = int((i / total_stocks) * 100)
            self.update_task_progress('running', progress, f"增量导入 {i}/{total_stocks} 只股票")

            # 使用配置的请求间隔，避免触发频率限制
            time.sleep(REQUEST_INTERVAL)

        self.update_task_progress('completed', 100,
                                  f"增量导入完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")
        logger.info(f"增量导入完成: 成功 {success_count}, 失败 {fail_count}, 总记录 {total_records}")


def main():
    parser = argparse.ArgumentParser(description='日线数据导入脚本')
    parser.add_argument('--code', type=str, help='股票代码（如 000001），不指定则导入全部')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--incremental', action='store_true', help='增量导入模式')

    args = parser.parse_args()

    importer = None
    try:
        importer = DailyDataImporter()
        if args.incremental:
            task_name = f"日线数据导入_增量_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            importer.create_task(task_name, {'mode': 'incremental'})
            logger.info("开始增量导入...")
            importer.incremental_import()
        else:
            if args.code:
                task_name = f"日线数据导入_单股_{args.code}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                importer.create_task(task_name, {'mode': 'single', 'code': args.code})
                logger.info(f"开始导入单股票: {args.code}")
                count = importer.import_stock_data(args.code, args.start, args.end)
                importer.update_task_progress('completed', 100, f"导入完成: {count} 条记录")
                logger.info(f"导入完成: {count} 条记录")
            else:
                task_name = f"日线数据导入_全量_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                importer.create_task(task_name, {'mode': 'full'})
                codes = importer.get_stock_list()
                logger.info(f"开始全量导入: {len(codes)} 只股票")
                importer.full_import(codes, args.start, args.end)
    except (KeyboardInterrupt, SystemExit):
        if importer:
            importer._interrupted = True
        logger.info("=" * 60)
        logger.info("⚠️  下载任务已被中断")
        logger.info("   已下载的数据已保存到数据库，不会丢失")
        logger.info("   下次运行时会自动从中断位置继续")
        logger.info("=" * 60)
        if importer:
            importer.update_task_progress('interrupted', 0, "任务被用户中断")
    except Exception as e:
        logger.error(f"程序异常: {e}")
        raise
    finally:
        if importer:
            importer.close()


if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
pytdx 日线数据全量下载脚本

从通达信下载全市场日线数据，写入 stock_quotes 表。
使用 pytdx 作为数据源，免费、无需 Token、无配额限制。

用法：
    # 全量下载（从头开始）
    PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py

    # 指定日期范围
    PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py --start 2026-01-01 --end 2026-07-17

    # 单只股票
    PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py --code 000001

    # 增量下载（最近30天）
    PYTHONPATH=backend ./venv/bin/python backend/collector/etl/import_tdx_daily.py --incremental

注意：
- pytdx 不支持北交所股票，自动跳过 8 开头的代码
- 每只股票下载最多 800 条K线（约3年），如需更多历史数据需分批下载
- 下载速度约 2-3 只/秒，全市场 5000+ 只约需 30-40 分钟
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import argparse
import json
import time
import pandas as pd
from datetime import datetime, timedelta
from collector.datasource.pytdx import PytdxDataSource, set_global_trade_calendar
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('tdx_import')


def get_stock_codes(storage: PostgreSQLStorage) -> list:
    """获取所有股票代码（排除北交所 8 开头）"""
    with storage.transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT code FROM stock_basic WHERE code NOT LIKE '8%' ORDER BY code"
            )
            return [row[0] for row in cursor.fetchall()]


def download_and_save(
    storage: PostgreSQLStorage,
    pytdx: PytdxDataSource,
    code: str,
    start_date: str = None,
    end_date: str = None,
) -> int:
    """
    下载单只股票日线数据并写入数据库。

    pytdx 代码格式要求：必须带 .SZ/.SH 后缀。
    stock_basic 中 code 为纯数字，需要根据前缀推断后缀（0/3→SZ, 6→SH）。
    """
    # 推断后缀
    if code.startswith(('0', '3')):
        tdx_code = f"{code}.SZ"
    elif code.startswith('6'):
        tdx_code = f"{code}.SH"
    else:
        logger.warning(f"跳过未知市场代码: {code}")
        return 0

    try:
        df = pytdx.get_kline(tdx_code, cycle='daily', start_date=start_date, end_date=end_date)
    except Exception as e:
        logger.warning(f"下载失败 {code}: {e}")
        return 0

    if df.empty:
        return 0

    # 补充必要字段
    df['code'] = code  # 使用纯数字代码
    df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta(hours=15)
    df['pre_close'] = df['close'].shift(1)
    df['adjust_type'] = 'qfq'

    # 确保数值类型正确
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)
    df['volume'] = df['volume'].astype(float).astype('int64')
    df['amount'] = df['amount'].astype(float)

    rows = storage.save_quotes(df)
    return rows


def main():
    parser = argparse.ArgumentParser(description='pytdx 日线数据下载')
    parser.add_argument('--code', type=str, help='单只股票代码（纯数字，如 000001）')
    parser.add_argument('--start', type=str, help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='结束日期 YYYY-MM-DD')
    parser.add_argument('--incremental', action='store_true', help='增量模式（仅下载最近30天）')
    args = parser.parse_args()

    # 数据库连接
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    storage.connect()
    storage.init_tables()

    # pytdx 连接
    pytdx = PytdxDataSource()
    if not pytdx.connect():
        logger.error("pytdx 连接失败，退出")
        return 1

    # 注入交易日历（从数据库获取）
    try:
        with storage.transaction() as conn:
            cal_df = pd.read_sql(
                "SELECT cal_date FROM trade_calendar WHERE is_open=1 ORDER BY cal_date",
                conn,
            )
            if not cal_df.empty:
                set_global_trade_calendar(cal_df)
    except Exception:
        pass  # trade_calendar 表可能不存在，不影响下载

    # 确定日期范围
    if args.incremental:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        logger.info(f"增量模式: {start_date} ~ {end_date}")
    else:
        start_date = args.start
        end_date = args.end

    # 单只股票模式
    if args.code:
        rows = download_and_save(storage, pytdx, args.code, start_date, end_date)
        print(f"\n单只股票 {args.code}: 写入 {rows} 条")
        print(f'TASK_RESULT:{json.dumps({"rows_affected": rows, "stock": args.code})}')
        pytdx.disconnect()
        storage.disconnect()
        return 0

    # 全市场模式
    codes = get_stock_codes(storage)
    total = len(codes)
    logger.info(f"共 {total} 只股票待下载（已排除北交所）")

    success = 0
    total_rows = 0
    start_time = time.time()

    for i, code in enumerate(codes):
        try:
            rows = download_and_save(storage, pytdx, code, start_date, end_date)
            if rows > 0:
                success += 1
                total_rows += rows
        except Exception as e:
            logger.warning(f"处理 {code} 异常: {e}")

        # 进度报告
        if (i + 1) % 100 == 0 or i == total - 1:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            logger.info(
                f"进度: {i+1}/{total} ({(i+1)/total*100:.1f}%), "
                f"成功 {success}, 记录 {total_rows}, "
                f"速度 {rate:.1f}只/秒, ETA {eta:.0f}秒"
            )

    elapsed = time.time() - start_time
    logger.info(f"完成: {success}/{total} 只, {total_rows} 条, 耗时 {elapsed:.0f}秒")
    print(f'TASK_RESULT:{json.dumps({"rows_affected": total_rows, "extra_metrics": {"success_stocks": success, "total_stocks": total, "elapsed_seconds": int(elapsed)}})}')

    pytdx.disconnect()
    storage.disconnect()
    return 0


if __name__ == '__main__':
    sys.exit(main())
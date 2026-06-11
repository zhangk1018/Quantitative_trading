#!/usr/bin/env python3
"""
sync_adj_factor.py - 复权因子同步脚本

从 Baostock 获取复权因子数据并更新到 stock_adj_factor 表。
Baostock query_adjust_factor 是按股票查询的，因此采用逐股票遍历方式。

使用说明：
  初次同步（全量历史）：python sync_adj_factor.py
  增量同步（最近30天）：python sync_adj_factor.py --incremental

注意：Tushare 免费版不支持 adj_factor 接口，已禁用。
"""

import sys
import os
import argparse

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import baostock as bs
import pandas as pd
from datetime import datetime, timedelta
from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('sync_adj_factor')


def get_active_stocks(source: BaostockDataSource) -> pd.DataFrame:
    """获取活跃股票列表"""
    try:
        stocks = source.get_stock_list()
        if stocks.empty:
            logger.error("❌ 获取股票列表为空")
            return pd.DataFrame()
        logger.info(f"📋 获取到 {len(stocks)} 只活跃股票")
        return stocks
    except Exception as e:
        logger.error(f"❌ 获取股票列表失败: {e}")
        return pd.DataFrame()


def _get_last_known_adj_factor(storage: PostgreSQLStorage, code: str) -> tuple:
    """获取股票最近一次的复权因子"""
    try:
        with storage.conn.cursor() as cur:
            cur.execute(
                "SELECT trade_date, adj_factor FROM stock_adj_factor "
                "WHERE code = %s ORDER BY trade_date DESC LIMIT 1",
                (code,)
            )
            row = cur.fetchone()
            if row:
                return (row[0], row[1])
    except Exception as e:
        print(f"  [EXCEPTION] {code}: _get_last_known_adj_factor 异常: {e}", flush=True)
    return (None, None)


def _fill_missing_dates(storage: PostgreSQLStorage, code: str, start_date: str, 
                        end_date: str, last_adj_factor: float) -> int:
    """
    当 Baostock 返回空数据时，前向填充缺失日期的复权因子
    
    注意：复权因子只在有分红、送股等事件时才会变化。如果没有事件，
    最近的复权因子在后续日期依然有效。
    
    Returns:
        int: 填充的记录数
    """
    if last_adj_factor is None:
        return 0
    
    # 获取数据库中该股票在日期范围内的已有记录
    # 注意：SQL 日期比较需要 YYYY-MM-DD 格式
    sql_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    sql_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
    try:
        with storage.conn.cursor() as cur:
            cur.execute(
                "SELECT trade_date FROM stock_adj_factor "
                "WHERE code = %s AND trade_date >= %s AND trade_date <= %s "
                "ORDER BY trade_date",
                (code, sql_start, sql_end)
            )
            existing_dates = set(row[0] for row in cur.fetchall())
    except Exception:
        existing_dates = set()
    
    # 生成需要填充的日期列表（排除已有的）
    from datetime import datetime, timedelta
    start_dt = datetime.strptime(start_date, '%Y%m%d')
    end_dt = datetime.strptime(end_date, '%Y%m%d')
    
    fill_dates = []
    current = start_dt
    while current <= end_dt:
        # trade_date 在数据库中存储为日期类型（无时间），比较时忽略时间部分
        from datetime import date
        date_obj = date(current.year, current.month, current.day)
        if date_obj not in existing_dates:
            fill_dates.append(date_obj)
        current += timedelta(days=1)
    
    if not fill_dates:
        return 0
    
    # 批量插入缺失日期的复权因子（使用最近已知值）
    from psycopg2.extras import execute_values
    values = [(code, d, last_adj_factor) for d in fill_dates]
    
    try:
        with storage.conn.cursor() as cur:
            execute_values(
                cur,
                "INSERT INTO stock_adj_factor (code, trade_date, adj_factor) "
                "VALUES %s ON CONFLICT (code, trade_date) DO UPDATE SET adj_factor = EXCLUDED.adj_factor",
                values
            )
        storage.conn.commit()
        return len(fill_dates)
    except Exception as e:
        print(f"  [EXCEPTION] {code}: _fill_missing_dates 异常: {e}", flush=True)
        storage.conn.rollback()
        return 0


def sync_stock_adj_factor(source: BaostockDataSource, storage: PostgreSQLStorage,
                          code: str, exchange: str, start_date: str, end_date: str,
                          fill_missing: bool = True, skip_api: bool = False) -> int:
    """
    同步单只股票的复权因子数据

    Returns:
        int: 保存的记录数
    """
    bs_code = f"{exchange.lower()}.{code}"

    if skip_api:
        # 跳过 Baostock API，直接从 DB 前向填充
        if fill_missing:
            _, last_adj = _get_last_known_adj_factor(storage, code)
            if last_adj is not None:
                filled = _fill_missing_dates(storage, code, start_date, end_date, last_adj)
                return filled
        return 0

    bs_start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    bs_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    source._wait_for_rate_limit()

    try:
        rs = bs.query_adjust_factor(code=bs_code, start_date=bs_start, end_date=bs_end)

        if rs.error_code != '0':
            logger.debug(f"  ⚠️ {code}: 查询失败 {rs.error_msg}")
            return 0

        data_list = []
        while (rs.error_code == '0') & rs.next():
            row_data = rs.get_row_data()
            # row_data = [code, dividOperateDate, adjfactor, turn, parValue]
            if len(row_data) >= 3 and row_data[2] and row_data[2] != '':
                data_list.append({
                    'code': code,
                    'trade_date': row_data[1].replace('-', '') if '-' in str(row_data[1]) else str(row_data[1]),
                    'adj_factor': float(row_data[2])
                })

        if not data_list:
            # Baostock 返回空：可能是无分红事件或 API 限制
            # 增量模式下，前向填充缺失日期的复权因子
            if fill_missing:
                _, last_adj = _get_last_known_adj_factor(storage, code)
                if last_adj is not None:
                    filled = _fill_missing_dates(storage, code, start_date, end_date, last_adj)
                    if filled > 0:
                        print(f"  [FILL] {code}: 前向填充 {filled} 个缺失日期的复权因子", flush=True)
                    return filled
                print(f"  [SKIP] {code}: 无历史复权因子可填充", flush=True)
            return 0

        # 存入临时 DataFrame 后保存
        df = pd.DataFrame(data_list)
        count = storage.save_adj_factor(df)
        return count

    except Exception as e:
        print(f"  [EXCEPTION] {code}: sync_stock_adj_factor 异常: {e}", flush=True)
        return 0


def sync_adj_factor(incremental: bool = False):
    """同步复权因子数据"""
    logger.info("=" * 60)
    logger.info("开始同步复权因子数据...")
    logger.info(f"模式: {'增量（最近30天）' if incremental else '全量历史'}")
    logger.info("=" * 60)

    # 初始化数据存储
    db_config = config.get('storage.postgresql', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', '990518')
    })
    if not storage.connect():
        logger.error("❌ 数据库连接失败")
        return
    storage.init_tables()

    # 连接 Baostock（只用于获取股票列表）
    source = BaostockDataSource()
    if not source.connect():
        logger.error("❌ Baostock 连接失败")
        storage.disconnect()
        return

    try:
        # 获取股票列表
        all_stocks = get_active_stocks(source)
        if all_stocks.empty:
            return

        # 确定日期范围
        today = datetime.now().strftime('%Y%m%d')
        if incremental:
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
        else:
            start_date = '20000101'
        end_date = today

        logger.info(f"📅 日期范围: {start_date} ~ {end_date}")

        if incremental:
            # 增量模式：从 DB 获取已有记录的股票，跳过 Baostock API
            logger.info("📋 增量模式：从数据库获取已有记录的股票...")
            with storage.conn.cursor() as cur:
                cur.execute("""
                    SELECT code, MAX(trade_date) as max_date 
                    FROM stock_adj_factor 
                    GROUP BY code 
                    ORDER BY code
                """)
                db_records = cur.fetchall()
            
            db_codes = set(r[0] for r in db_records)
            stock_max_dates = {r[0]: str(r[1]) for r in db_records}
            stocks_to_process = [s for s in all_stocks.itertuples() if s.code in db_codes]
            logger.info(f"  Baostock 总股票: {len(all_stocks)}, "
                        f"DB 已有记录: {len(db_codes)}, "
                        f"需要处理: {len(stocks_to_process)}")
        else:
            # 全量模式：处理所有股票
            stocks_to_process = list(all_stocks.itertuples())

        sql_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

        total_saved = 0
        total_with_data = 0
        total_skipped = 0
        total_stocks = len(stocks_to_process)
        skipped_ids = []

        for idx, s in enumerate(stocks_to_process):
            code = s.code

            # 检查是否已是最新
            if incremental:
                max_date = stock_max_dates.get(code)
                if max_date and max_date >= sql_end:
                    total_skipped += 1
                    skipped_ids.append(idx)
                    if len(skipped_ids) <= 5:
                        print(f"  [SKIP_UP2DATE] {code}: max_date={max_date} >= end_date={sql_end}", flush=True)
                    continue

            count = sync_stock_adj_factor(source, storage, code, 
                                          getattr(s, 'exchange', 'SH' if code.startswith('6') else 'SZ'),
                                          start_date, end_date,
                                          fill_missing=incremental,
                                          skip_api=incremental)
            if count > 0:
                total_saved += count
                total_with_data += 1

            if (idx + 1) % 100 == 0:
                logger.info(f"  📊 进度: {idx+1}/{total_stocks} | "
                            f"已处理: {total_with_data} 只 | "
                            f"已跳过(最新): {total_skipped} 只 | "
                            f"总记录: {total_saved} 条")

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 复权因子同步完成")
        logger.info(f"  处理股票: {total_with_data} 只")
        logger.info(f"  已跳过(最新): {total_skipped} 只")
        logger.info(f"  总记录数: {total_saved} 条")
        logger.info(f"{'='*60}")

    except Exception as e:
        logger.error(f"❌ 同步复权因子失败: {e}")
    finally:
        source.disconnect()
        storage.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='同步复权因子数据')
    parser.add_argument('--incremental', action='store_true', help='增量模式（最近30天）')
    args = parser.parse_args()
    sync_adj_factor(incremental=args.incremental)
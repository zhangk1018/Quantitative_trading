#!/usr/bin/env python3
"""
科创板等缺失数据补全脚本 - 使用 Baostock 下载补全

思路：
1. 从 stock_basic 获取全部股票，左连接 stock_quotes 统计每个股票的数据天数
2. 筛选出数据不足（或完全缺失）的股票
3. 使用 Baostock 为这些股票补全全量历史数据
4. 支持指定日期范围检查、试运行(dry-run)、断点续传

用法：
python scripts/fill_missing_data.py                                  # 补全所有历史数据不足60天的股票
python scripts/fill_missing_data.py --start-date 2026-01-01 --end-date 2026-06-30 --min-days 100  # 补全2026年上半年数据不足100天的股票
python scripts/fill_missing_data.py --code 688001                    # 单只补全
python scripts/fill_missing_data.py --market kcb --dry-run           # 试运行：仅查看科创板需补全的股票
"""
import sys
import os
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import argparse
import time
import pandas as pd
from datetime import datetime
from typing import List, Optional
from psycopg2.extras import execute_values

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger

logger = setup_logger('data_filler')


def get_missing_stocks(storage: PostgreSQLStorage, min_days: int = 60, market: Optional[str] = None,
                       start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[str]:
    """
    获取数据不足的股票列表（从 stock_basic 表出发，包括完全没有数据的股票）
    
    Args:
        storage: 数据库连接
        min_days: 指定日期范围内的最少交易日数
        market: 市场筛选，可选：kcb(688), cyb(300), sh(6), sz(00)
        start_date: 检查起始日期 (YYYY-MM-DD)
        end_date: 检查结束日期 (YYYY-MM-DD)
        
    Returns:
        股票代码列表（6位纯数字，不带后缀）
    """
    # 构建市场筛选条件（基于股票代码前缀，排除北交所）
    where_conds = [
        "sb.code NOT LIKE '8%%'",
        "sb.code NOT LIKE '43%%'",
        "sb.code NOT LIKE '92%%'",
        "sb.delist_date IS NULL"  # 排除已退市股票
    ]
    
    if market == 'kcb':
        where_conds.append("sb.code LIKE '688%%'")
    elif market == 'cyb':
        where_conds.append("sb.code LIKE '300%%'")
    elif market == 'sh':
        where_conds.append("sb.code LIKE '6%%' AND sb.code NOT LIKE '688%%'")
    elif market == 'sz':
        where_conds.append("sb.code LIKE '00%%'")
        
    where_clause = " AND ".join(where_conds)
    
    # 根据是否指定日期范围，构建不同的查询
    if start_date and end_date:
        # 检查特定日期范围内的数据天数
        query = f"""
            SELECT sb.code
            FROM stock_basic sb
            LEFT JOIN (
                SELECT code, COUNT(DISTINCT trade_date) AS data_days
                FROM stock_quotes
                WHERE cycle = '1d'
                  AND trade_date >= %s
                  AND trade_date <= %s
                GROUP BY code
            ) sq ON sb.code = sq.code
            WHERE {where_clause}
              AND (sq.data_days IS NULL OR sq.data_days < %s)
            ORDER BY sb.code
        """
        params = (start_date, end_date, min_days)
        logger.debug(f"检查日期范围: {start_date} ~ {end_date}, 阈值: {min_days} 天")
    else:
        # 检查全量历史数据天数
        query = f"""
            SELECT sb.code
            FROM stock_basic sb
            LEFT JOIN (
                SELECT code, COUNT(DISTINCT trade_date) AS data_days
                FROM stock_quotes 
                WHERE cycle = '1d' 
                GROUP BY code
            ) sq ON sb.code = sq.code
            WHERE {where_clause}
              AND (sq.data_days IS NULL OR sq.data_days < %s)
            ORDER BY sb.code
        """
        params = (min_days,)
        logger.debug(f"检查全量历史, 阈值: {min_days} 天")

    with storage.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            codes = [row[0] for row in cur.fetchall()]
    return codes


def _strip_suffix(code: str) -> str:
    """移除股票代码后缀（如 .SH/.SZ/.BJ），返回6位数字"""
    if '.' in code:
        return code.split('.')[0]
    return code


def _add_suffix(code: str) -> str:
    """为6位数字股票代码添加后缀"""
    if '.' in code:
        return code
    if code.startswith('6'):
        return f"{code}.SH"
    elif code.startswith('0') or code.startswith('3'):
        return f"{code}.SZ"
    # 支持北交所 8 开头和 920 开头
    elif code.startswith('8') or code.startswith('920'):
        return f"{code}.BJ"
    else:
        return code


def import_stock_via_baostock(storage: PostgreSQLStorage, ds: BaostockDataSource, code: str,
                              start_date: str = '2000-01-01',
                              end_date: Optional[str] = None) -> int:
    """
    使用 Baostock 导入单只股票的完整日线数据（增量）
    复用外部传入的 BaostockDataSource 连接，避免频繁 login/logout
    
    Args:
        storage: 数据库连接
        ds: 已连接的 BaostockDataSource 实例
        code: 股票代码（6位或带后缀格式）
        start_date: 起始日期
        end_date: 结束日期，默认为当天
        
    Returns:
        导入的记录数
    """
    full_code = code
    try:
        full_code = _add_suffix(code)
        code6 = _strip_suffix(code)
        
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # 获取数据库中该股票在指定日期范围已存在的所有日期
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT trade_date
                    FROM stock_quotes
                    WHERE code = %s AND cycle = '1d'
                      AND trade_date >= %s AND trade_date <= %s
                """, (code6, start_date, end_date))
                existing_dates = {row[0] for row in cur.fetchall()}
        
        logger.debug(f"  {full_code}: 数据库中在 {start_date} 到 {end_date} 已有 {len(existing_dates)} 天数据")

        # 添加简单的重试机制
        df = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                df = ds.get_kline(code=code6, cycle='daily', start_date=start_date, end_date=end_date)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                logger.warning(f"  {full_code}: 获取数据失败 (尝试 {attempt+1}/{max_retries}): {e}")
                time.sleep(2 ** attempt)

        if df is None or df.empty:
            logger.warning(f"  {full_code}: Baostock 无数据")
            return 0

        # 处理 Baostock 返回的 preclose 字段
        if 'preclose' in df.columns:
            df = df.rename(columns={'preclose': 'pre_close'})
        # 标准化日期列名
        if 'date' in df.columns:
            df = df.rename(columns={'date': 'trade_date'})

        # 格式化数据
        numeric_cols = ['open', 'high', 'low', 'close', 'amount']
        if 'pre_close' in df.columns:
            numeric_cols.append('pre_close')
            
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        # 过滤无效数据
        price_cols = ['open', 'high', 'low', 'close']
        mask = (df[price_cols] > 0).all(axis=1) & df['volume'].notna() & (df['volume'] > 0)
        df = df[mask]

        # 只保留数据库中不存在的日期
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        new_data_mask = ~df['trade_date'].isin(existing_dates)
        df_new = df[new_data_mask].copy()

        if df_new.empty:
            logger.info(f"  {full_code}: 无新数据需要导入")
            return 0

        logger.info(f"  {full_code}: 发现 {len(df_new)} 条新数据")

        # 添加元数据
        df_new['code'] = code6
        df_new['cycle'] = '1d'
        df_new['adjust_type'] = 'qfq'

        # 安全导入
        import_count = _safe_import_quotes(storage, df_new, full_code)
        return import_count

    except Exception as e:
        logger.error(f"  {full_code}: 导入失败: {e}")
        return 0


def _safe_import_quotes(storage: PostgreSQLStorage, df: pd.DataFrame, code: str) -> int:
    """
    安全导入行情数据，使用 execute_values 批量插入，避免重复键冲突
    使用 RETURNING 获取实际插入行数
    缺失列填充 None 而非 0
    """
    if df.empty:
        return 0

    # 确保列存在
    cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
            'pre_close', 'volume', 'amount', 'adjust_type', 'trade_datetime']
    for col in cols:
        if col not in df.columns:
            df[col] = None

    # 向量化处理时间
    df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta(hours=15)
    # 将 NaN/NaT 转换为 None
    df = df.where(pd.notnull(df), None)

    # 转换为 tuple 列表
    data_tuples = [tuple(x) for x in df[cols].to_numpy()]

    insert_sql = """
        INSERT INTO stock_quotes (
            code, cycle, trade_date, open, high, low, close,
            pre_close, volume, amount, adjust_type, trade_datetime
        ) VALUES %s
        ON CONFLICT (code, cycle, trade_date) DO NOTHING
        RETURNING code
    """
    
    try:
        with storage.transaction() as conn:
            with conn.cursor() as cur:
                execute_values(cur, insert_sql, data_tuples, page_size=1000)
                import_count = len(cur.fetchall())
        return import_count
    except Exception as e:
        logger.error(f"  {code}: 批量导入失败: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='缺失数据补全脚本')
    parser.add_argument('--code', type=str, help='单只股票代码')
    parser.add_argument('--market', type=str, choices=['kcb', 'cyb', 'sh', 'sz'],
                        help='市场筛选：kcb(科创板), cyb(创业板), sh(上证), sz(深证)')
    parser.add_argument('--min-days', type=int, default=60, 
                        help='指定日期范围内最少交易日数，低于此值的将被补全')
    parser.add_argument('--start-date', type=str, 
                        help='检查数据缺失的起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, 
                        help='检查数据缺失的结束日期 (YYYY-MM-DD)')
    parser.add_argument('--start', type=int, default=0, 
                        help='从第几只开始（断点续传，跳过前 N 只）')
    parser.add_argument('--limit', type=int, default=0, 
                        help='限制补全数量')
    parser.add_argument('--dry-run', action='store_true', 
                        help='试运行模式：仅打印需补全的股票，不实际导入')
    args = parser.parse_args()

    # 连接数据库
    db_config = config.get('database', {})
    storage = PostgreSQLStorage({
        'host': db_config.get('host', 'localhost'),
        'port': db_config.get('port', 5432),
        'database': db_config.get('database', 'quant_trading'),
        'username': db_config.get('username', 'quant_user'),
        'password': db_config.get('password', ''),
    })
    storage.connect()

    try:
        if args.code:
            # 单只股票补全
            logger.info(f"补全单只股票: {args.code}")
            ds = BaostockDataSource()
            ds.connect()
            try:
                count = import_stock_via_baostock(storage, ds, args.code)
                logger.info(f"  {args.code}: 导入 {count} 条记录")
            finally:
                ds.disconnect()
        else:
            # 批量补全
            codes = get_missing_stocks(
                storage, 
                min_days=args.min_days, 
                market=args.market,
                start_date=args.start_date,
                end_date=args.end_date
            )
            
            total = len(codes)
            if total == 0:
                logger.info("没有需要补全的股票 ✅")
                return

            # 断点续传与限制
            start_idx = args.start
            if start_idx > 0:
                codes = codes[start_idx:]
            if args.limit > 0:
                codes = codes[:args.limit]

            logger.info(f"需补全股票: {len(codes)} 只（从 #{start_idx} 开始）")
            
            # Dry-run 模式
            if args.dry_run:
                logger.info("🔍 [DRY-RUN] 试运行模式，以下股票将被补全：")
                for i, code in enumerate(codes):
                    logger.info(f"  [{i+1}] {code}")
                logger.info(f"共计 {len(codes)} 只股票。取消 --dry-run 参数以执行实际导入。")
                return

            # 全局复用 Baostock 连接
            ds = BaostockDataSource()
            ds.connect()
            
            success = 0
            fail = 0
            total_records = 0
            
            try:
                for i, code in enumerate(codes):
                    logger.info(f"  [{start_idx+i+1}/{total}] 补全 {code}...")
                    
                    imp_start = args.start_date or '2000-01-01'
                    imp_end = args.end_date or datetime.now().strftime('%Y-%m-%d')
                    
                    count = import_stock_via_baostock(storage, ds, code, 
                                                      start_date=imp_start, 
                                                      end_date=imp_end)
                    if count > 0:
                        success += 1
                        total_records += count
                        logger.info(f"    ✅ 导入 {count} 条")
                    else:
                        fail += 1

                    if (i + 1) % 50 == 0:
                        logger.info(f"  进度: {i+1}/{len(codes)}, 成功 {success}, 失败 {fail}, 记录 {total_records}")
                        
                    # 简单限流，防止 Baostock 封禁
                    if i % 10 == 9:
                        time.sleep(0.5)
            finally:
                ds.disconnect()

            logger.info("=" * 60)
            logger.info("📊 补全完成")
            logger.info(f"  处理: {len(codes)} 只")
            logger.info(f"  成功: {success} 只")
            logger.info(f"  失败: {fail} 只")
            logger.info(f"  记录: {total_records} 条")
            logger.info("=" * 60)
            
    finally:
        storage.disconnect()


if __name__ == '__main__':
    main()
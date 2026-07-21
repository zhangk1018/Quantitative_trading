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
import json
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import argparse
import time
import pandas as pd
from datetime import datetime
from typing import List, Optional
from psycopg2.extras import execute_values

from collector.datasource.baostock import BaostockDataSource
from collector.datasource.tushare import TushareDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger
from utils.stock_code_utils import normalize_code, filter_out_bse

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


def import_missing_via_tushare_batch(storage: PostgreSQLStorage, codes: List[str],
                                     trade_date: str) -> dict:
    """
    使用 Tushare 批量接口补全指定日期缺失的股票数据（不复权 → 前复权）

    Args:
        storage: PostgreSQL 存储实例
        codes: 需要补全的 6 位股票代码列表
        trade_date: 目标交易日 YYYY-MM-DD

    Returns:
        dict: {'success': int, 'fail': int, 'rows_affected': int}
    """
    result = {'success': 0, 'fail': 0, 'rows_affected': 0}
    if not codes:
        return result

    ds = TushareDataSource()
    if not ds.connect():
        logger.error("Tushare Pro 连接失败，无法补全缺失数据")
        return result

    try:
        logger.info(f"🚀 使用 Tushare 批量接口补全 {trade_date} 的 {len(codes)} 只缺失股票")
        df = ds.batch_get_daily(trade_date)
        if df is None or df.empty:
            logger.warning(f"⚠️ Tushare 未返回 {trade_date} 数据")
            return result

        # 字段标准化
        rename_map = {'ts_code': 'code', 'vol': 'volume'}
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df['code'] = df['code'].apply(lambda x: normalize_code(x) or x)
        df['trade_date'] = df['trade_date'].str.replace(r'(\d{4})(\d{2})(\d{2})', r'\1-\2-\3', regex=True)

        # 过滤只保留目标缺失股票
        target_codes = set(codes)
        df = df[df['code'].isin(target_codes)].copy()
        if df.empty:
            logger.warning("⚠️ Tushare 返回数据中不包含目标缺失股票")
            return result

        # 过滤北交所并清洗
        df, _ = filter_out_bse(df)

        # 数值转换
        numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 'amount']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce') * 100

        # 过滤无效数据
        price_cols = ['open', 'high', 'low', 'close']
        mask = (df[price_cols] > 0).all(axis=1) & df['volume'].notna() & (df['volume'] > 0)
        df = df[mask].copy()
        if df.empty:
            logger.warning("⚠️ 数据清洗后为空")
            return result

        # 前复权转换
        df = _apply_qfq_for_tushare_batch(storage, df, trade_date)
        if df is None or df.empty:
            logger.warning("⚠️ 复权转换后数据为空")
            return result

        df['cycle'] = '1d'
        df['adjust_type'] = 'qfq'
        df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta(hours=15)
        df['volume'] = df['volume'].round().astype('Int64')

        inserted = _safe_import_quotes(storage, df, 'TUSHARE_BATCH')
        result['rows_affected'] = inserted
        result['success'] = inserted > 0
        logger.info(f"✅ Tushare 批量补全完成：插入 {inserted} 条记录")
        return result
    finally:
        ds.disconnect()


def _import_single_via_tushare(storage: PostgreSQLStorage, code: str,
                               start_date: str, end_date: str) -> int:
    """
    使用 Tushare 单只接口补全数据（不复权 → 前复权）
    """
    ds = TushareDataSource()
    if not ds.connect():
        logger.error("Tushare Pro 连接失败")
        return 0
    try:
        df = ds.get_kline(code=code, cycle='daily', start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return 0

        # 字段标准化
        rename_map = {'ts_code': 'code', 'vol': 'volume'}
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        if 'code' not in df.columns:
            df['code'] = code
        df['code'] = df['code'].apply(lambda x: normalize_code(x) or x)
        if 'trade_date' in df.columns:
            df['trade_date'] = df['trade_date'].str.replace(r'(\d{4})(\d{2})(\d{2})', r'\1-\2-\3', regex=True)

        # 数值转换
        numeric_cols = ['open', 'high', 'low', 'close', 'amount']
        if 'pre_close' in df.columns:
            numeric_cols.append('pre_close')
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce') * 100

        # 过滤无效数据
        price_cols = ['open', 'high', 'low', 'close']
        mask = (df[price_cols] > 0).all(axis=1) & df['volume'].notna() & (df['volume'] > 0)
        df = df[mask].copy()
        if df.empty:
            return 0

        # 前复权转换：逐日处理
        df = _apply_qfq_for_tushare_batch(storage, df, df['trade_date'].iloc[-1])
        if df is None or df.empty:
            return 0

        df['cycle'] = '1d'
        df['adjust_type'] = 'qfq'
        df['trade_datetime'] = pd.to_datetime(df['trade_date']) + pd.Timedelta(hours=15)
        df['volume'] = df['volume'].round().astype('Int64')

        return _safe_import_quotes(storage, df, code)
    finally:
        ds.disconnect()


def _apply_qfq_for_tushare_batch(storage: PostgreSQLStorage, df: pd.DataFrame,
                                 trade_date: str) -> pd.DataFrame:
    """
    对 Tushare 批量数据执行前复权转换（复用 stock_adj_factor 表）
    """
    codes = df['code'].unique().tolist()
    with storage.transaction() as conn:
        with conn.cursor() as cur:
            placeholders = ','.join(['%s'] * len(codes))
            cur.execute(f"""
                SELECT code, adj_factor FROM stock_adj_factor
                WHERE code IN ({placeholders}) AND trade_date = %s
            """, codes + [trade_date])
            date_adj = {row[0]: float(row[1]) for row in cur.fetchall()}

            cur.execute(f"""
                SELECT DISTINCT ON (code) code, adj_factor
                FROM stock_adj_factor
                WHERE code IN ({placeholders})
                ORDER BY code, trade_date DESC
            """, codes)
            latest_adj = {row[0]: float(row[1]) for row in cur.fetchall()}

    df['adj_factor_date'] = df['code'].map(date_adj).fillna(1.0)
    df['adj_factor_latest'] = df['code'].map(latest_adj).fillna(1.0)
    ratio = df['adj_factor_date'] / df['adj_factor_latest'].replace(0, 1.0)

    price_cols = ['open', 'high', 'low', 'close']
    if 'pre_close' in df.columns:
        price_cols.append('pre_close')
    for col in price_cols:
        if col in df.columns:
            df[col] = (df[col].astype(float) * ratio).round(2)

    return df.drop(columns=['adj_factor_date', 'adj_factor_latest'], errors='ignore')


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
    parser.add_argument('--use-tushare', action='store_true',
                        help='使用 Tushare 批量接口补全（Baostock 不可用时降级）')
    args = parser.parse_args()

    # 连接数据库：优先从配置读取，缺失时从环境变量构建
    db_config = config.get('storage.postgresql')
    if not db_config:
        db_config = {
            'host': os.getenv('PG_HOST', 'localhost'),
            'port': int(os.getenv('PG_PORT', 5432)),
            'database': os.getenv('PG_DATABASE', 'quant_trading'),
            'username': os.getenv('PG_USER', 'quant_user'),
            'password': os.getenv('PG_PASSWORD', ''),
        }
    storage = PostgreSQLStorage(db_config)
    storage.connect()

    try:
        if args.code:
            # 单只股票补全
            logger.info(f"补全单只股票: {args.code}")
            if args.use_tushare:
                count = _import_single_via_tushare(storage, args.code,
                                                   args.start_date or '2020-01-01',
                                                   args.end_date or datetime.now().strftime('%Y-%m-%d'))
            else:
                ds = BaostockDataSource()
                ds.connect()
                try:
                    count = import_stock_via_baostock(storage, ds, args.code)
                finally:
                    ds.disconnect()
            logger.info(f"  {args.code}: 导入 {count} 条记录")
            print(f'TASK_RESULT:{json.dumps({"rows_affected": count, "extra_metrics": {"code": args.code}})}')
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
                print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": {"total": 0, "success": 0, "fail": 0}})}')
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

            if args.use_tushare:
                # Tushare 批量接口补全（适合单日缺失场景）
                trade_date = args.end_date or args.start_date
                if not trade_date:
                    logger.error("❌ 使用 --use-tushare 时必须指定 --start-date 或 --end-date")
                    print(f'TASK_RESULT:{json.dumps({"rows_affected": 0, "extra_metrics": {"error": "missing trade_date"}})}')
                    return
                result = import_missing_via_tushare_batch(storage, codes, trade_date)
                total_records = result['rows_affected']
                success = result['success']
                fail = len(codes) - success
                print(f'TASK_RESULT:{json.dumps({"rows_affected": total_records, "extra_metrics": {"total": len(codes), "success": success, "fail": fail}})}')
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
            print(f'TASK_RESULT:{json.dumps({"rows_affected": total_records, "extra_metrics": {"total": len(codes), "success": success, "fail": fail}})}')
            
    finally:
        storage.disconnect()


if __name__ == '__main__':
    main()
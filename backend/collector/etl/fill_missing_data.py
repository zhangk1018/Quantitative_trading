#!/usr/bin/env python3
"""
科创板等缺失数据补全脚本 - 使用 Baostock 下载补全

思路：
1. 从 stock_quotes 统计哪些股票数据不足 60 个交易日
2. 使用 Baostock 为这些股票补全全量历史数据
3. 科创板(688xxx) 为重点补全对象

用法：
    python scripts/fill_missing_data.py                    # 补全所有数据不足的股票
    python scripts/fill_missing_data.py --code 688001      # 单只补全
    python scripts/fill_missing_data.py --market kcb       # 仅科创板
"""
import sys
import os
# 脚本位于 backend/collector/etl/fill_missing_data.py
# backend 目录为 ../../.. => backend 父目录/sibling backend
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

import argparse
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional

from collector.datasource.baostock import BaostockDataSource
from collector.storage.postgresql_storage import PostgreSQLStorage
from utils.config import config
from utils.logger import setup_logger
from utils.stock_code_utils import normalize_code

logger = setup_logger('data_filler')


def get_missing_stocks(storage: PostgreSQLStorage, min_days: int = 60, market: Optional[str] = None, 
                     check_2026_range: bool = False) -> List[str]:
    """获取数据不足的股票列表
    
    Args:
        storage: 数据库连接
        min_days: 最少交易日数
        market: 市场筛选，可选：kcb(688), cyb(300), bj(8xx), sh(6), sz(00)
        check_2026_range: 是否专门检查2026年1-5月数据
    
    Returns:
        股票代码列表（带后缀格式，如 688001.SH）
    """
    cursor = storage.conn.cursor()
    
    if check_2026_range:
        # 专门检查2026年1-5月数据不足的股票
        query = """
            SELECT sb.code
            FROM stock_basic sb
            LEFT JOIN (
                SELECT code, COUNT(DISTINCT trade_date) AS data_days_2026
                FROM stock_quotes
                WHERE cycle = '1d' 
                    AND trade_date >= '2026-01-01' 
                    AND trade_date <= '2026-05-31'
                GROUP BY code
            ) sq ON sb.code = sq.code
            WHERE sq.data_days_2026 IS NULL OR sq.data_days_2026 < %s
            ORDER BY sb.code
        """
        cursor.execute(query, (min_days,))
    else:
        # 构建 WHERE 条件
        where_conds = []
        
        # 排除北交所(BJ)代码段：8xx, 43xx, 92xx（数据源不覆盖或质量低）
        where_conds.append("sq.code NOT LIKE '8%'")
        where_conds.append("sq.code NOT LIKE '43%'")
        where_conds.append("sq.code NOT LIKE '92%'")

        if market == 'kcb':
            where_conds.append("sq.code LIKE '688%'")
        elif market == 'cyb':
            where_conds.append("sq.code LIKE '300%'")
        elif market == 'bj':
            where_conds.append("(sq.code LIKE '8%' OR sq.code LIKE '92%' OR sq.code LIKE '43%')")
        elif market == 'sh':
            where_conds.append("sq.code LIKE '6%' AND sq.code NOT LIKE '688%'")
        elif market == 'sz':
            where_conds.append("sq.code LIKE '00%'")
        
        where_clause = " AND ".join(where_conds) if where_conds else "TRUE"
        
        # 直接使用字符串格式化，避免参数占位符问题
        query = f"""
            SELECT sq.code
            FROM stock_quotes sq
            WHERE {where_clause}
            GROUP BY sq.code
            HAVING COUNT(*) < {min_days}
            ORDER BY sq.code
        """
        
        cursor.execute(query)
    
    codes = [row[0] for row in cursor.fetchall()]
    cursor.close()
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
    elif code.startswith('8'):
        return f"{code}.BJ"
    else:
        return code


def import_stock_via_baostock(storage: PostgreSQLStorage, code: str, 
                              start_date: str = '2000-01-01',
                              end_date: Optional[str] = None) -> int:
    """使用 Baostock 导入单只股票的完整日线数据（增量）
    
    Args:
        storage: 数据库连接
        code: 股票代码（6位或带后缀格式）
        start_date: 起始日期
        end_date: 结束日期，默认为当天
    
    Returns:
        导入的记录数
    """
    try:
        full_code = _add_suffix(code)
        code6 = _strip_suffix(code)
        
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # 第一步：获取数据库中该股票在指定日期范围已存在的所有日期
        cursor = storage.conn.cursor()
        cursor.execute("""
            SELECT DISTINCT trade_date 
            FROM stock_quotes 
            WHERE code = %s AND cycle = '1d'
                AND trade_date >= %s AND trade_date <= %s
        """, (code6, start_date, end_date))
        existing_dates = {row[0] for row in cursor.fetchall()}
        cursor.close()
        logger.debug(f"  {full_code}: 数据库中在 {start_date} 到 {end_date} 已有 {len(existing_dates)} 天数据")
        
        ds = BaostockDataSource()
        ds.connect()
        
        df = ds.get_kline(code=code6, cycle='daily', start_date=start_date, end_date=end_date)
        ds.disconnect()
        
        if df is None or df.empty:
            logger.warning(f"  {full_code}: Baostock 无数据")
            return 0
        
        # 格式化数据（参考 import_daily_data.py 的 _process_kline_data）
        numeric_cols = ['open', 'high', 'low', 'close', 'amount']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        
        # volume 列需要特殊处理
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['volume'] = df['volume'].where(
            df['volume'].notna() & df['volume'].notnull() & 
            (df['volume'] != float('inf')) & (df['volume'] != float('-inf')), 
            None
        )
        valid_mask = df['volume'].notna()
        if valid_mask.any():
            df.loc[valid_mask, 'volume'] = df.loc[valid_mask, 'volume'].astype('Int64')
        
        # 过滤无效数据
        price_cols = ['open', 'high', 'low', 'close']
        mask = (df[price_cols] > 0).all(axis=1) & df['volume'].notna() & (df['volume'] > 0)
        df = df[mask]
        
        # 第二步：只保留数据库中不存在的日期的数据
        df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
        new_data_mask = ~df['trade_date'].isin(existing_dates)
        df_new = df[new_data_mask].copy()
        
        if df_new.empty:
            logger.info(f"  {full_code}: 无新数据需要导入")
            return 0
        
        logger.info(f"  {full_code}: 发现 {len(df_new)} 条新数据")
        
        # 添加元数据（统一为纯数字格式）
        df_new['code'] = code6  # 纯6位数字，不带后缀
        df_new['cycle'] = '1d'
        df_new['adjust_type'] = 'qfq'
        
        # 确保列顺序正确
        cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
                'pre_close', 'volume', 'amount', 'adjust_type']
        for col in cols:
            if col not in df_new.columns:
                df_new[col] = 0 if col in ('volume', 'amount') else 0.0
        
        df_new = df_new[cols]
        
        # 第三步：先删除该股票可能有冲突的日期（以防万一），再导入
        # 使用逐行 INSERT ON CONFLICT 或临时表方式导入
        # 这里我们实现一个安全的导入方式：分批导入并跳过重复
        import_count = _safe_import_quotes(storage, df_new, full_code)
        return import_count
        
    except Exception as e:
        logger.error(f"  {full_code if 'full_code' in locals() else code}: 导入失败: {e}")
        return 0


def _safe_import_quotes(storage: PostgreSQLStorage, df: pd.DataFrame, code: str) -> int:
    """安全导入行情数据，避免重复键冲突
    
    Args:
        storage: 数据库连接
        df: 要导入的数据
        code: 股票代码（用于日志）
    
    Returns:
        成功导入的记录数
    """
    import_count = 0
    
    if df.empty:
        return 0
    
    try:
        # 方法一：逐行 INSERT ON CONFLICT DO NOTHING
        cursor = storage.conn.cursor()
        
        insert_sql = """
            INSERT INTO stock_quotes (
                code, cycle, trade_date, open, high, low, close,
                pre_close, volume, amount, adjust_type, trade_datetime
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code, cycle, trade_date, trade_datetime) DO NOTHING
        """
        
        for _, row in df.iterrows():
            # 构造 trade_datetime
            trade_datetime = pd.to_datetime(row['trade_date']) + pd.Timedelta('15:00:00')
            
            params = (
                row['code'],
                row['cycle'],
                row['trade_date'],
                float(row['open']) if pd.notna(row['open']) else 0.0,
                float(row['high']) if pd.notna(row['high']) else 0.0,
                float(row['low']) if pd.notna(row['low']) else 0.0,
                float(row['close']) if pd.notna(row['close']) else 0.0,
                float(row['pre_close']) if pd.notna(row['pre_close']) else 0.0,
                int(row['volume']) if pd.notna(row['volume']) else 0,
                float(row['amount']) if pd.notna(row['amount']) else 0.0,
                row['adjust_type'],
                trade_datetime
            )
            
            cursor.execute(insert_sql, params)
            if cursor.rowcount > 0:
                import_count += 1
        
        storage.conn.commit()
        cursor.close()
        logger.debug(f"  {code}: 成功导入 {import_count} 条新记录")
        return import_count
        
    except Exception as e:
        storage.conn.rollback()
        logger.error(f"  {code}: 安全导入失败: {e}")
        return 0


def import_stock_via_importer(storage: PostgreSQLStorage, code: str) -> int:
    """使用已有的 DailyDataImporter（Tushare→Baostock 备用）导入
    
    Args:
        storage: 数据库连接
        code: 6位数字股票代码
    
    Returns:
        导入的记录数
    """
    try:
        # 复用 DataSourceManager（Tushare 优先，Baostock 备用）
        from collector.datasource.base import DataSourceManager, SwitchStrategy
        from collector.datasource.tushare import TushareDataSource
        
        manager = DataSourceManager(
            sources=[
                {'source': TushareDataSource(), 'weight': 1, 'priority': 0},
                {'source': BaostockDataSource(), 'weight': 1, 'priority': 1}
            ],
            strategy=SwitchStrategy.FAILOVER
        )
        manager.connect()
        
        df = manager.get_kline(code=code, cycle='daily',
                               start_date='2000-01-01',
                               end_date=datetime.now().strftime('%Y-%m-%d'))
        manager.disconnect()
        
        if df is None or df.empty:
            logger.warning(f"  {code}: 无数据")
            return 0
        
        # 格式化
        df['code'] = code
        df['cycle'] = '1d'
        df['adjust_type'] = 'qfq'
        
        cols = ['code', 'cycle', 'trade_date', 'open', 'high', 'low', 'close',
                'pre_close', 'volume', 'amount', 'adjust_type']
        for col in cols:
            if col not in df.columns:
                df[col] = 0 if col in ('volume', 'amount') else 0.0
        df = df[cols]
        
        count = storage.save_quotes(df)
        return count
        
    except Exception as e:
        logger.error(f"  {code}: 导入失败: {e}")
        return 0


def main():
    parser = argparse.ArgumentParser(description='缺失数据补全脚本')
    parser.add_argument('--code', type=str, help='单只股票代码')
    parser.add_argument('--market', type=str, choices=['kcb', 'cyb', 'bj', 'sh', 'sz'],
                        help='市场筛选：kcb(科创板), cyb(创业板), bj(北交所), sh(上证), sz(深证)')
    parser.add_argument('--min-days', type=int, default=60, help='最少交易日数，低于此值的将被补全')
    parser.add_argument('--force', action='store_true', help='强制补全所有股票（不检查数据天数）')
    parser.add_argument('--start', type=str, default='0', help='从第几只开始（断点续传）')
    parser.add_argument('--limit', type=int, default=0, help='限制补全数量')
    parser.add_argument('--check-2026', action='store_true', 
                        help='专门检查并补全2026年1月-5月数据不足的股票')
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
    
    if args.code:
        # 单只股票补全
        logger.info(f"补全单只股票: {args.code}")
        count = import_stock_via_baostock(storage, args.code)
        logger.info(f"  {args.code}: 导入 {count} 条记录")
    else:
        # 批量补全
        if args.force:
            # 强制补全：从 stock_list 取所有股票
            cursor = storage.conn.cursor()
            cursor.execute("SELECT code FROM stock_list ORDER BY code")
            codes = [row[0] for row in cursor.fetchall()]
            cursor.close()
            logger.info(f"强制补全模式：stock_list 共 {len(codes)} 只")
        else:
            codes = get_missing_stocks(storage, min_days=args.min_days, market=args.market, 
                                     check_2026_range=args.check_2026)
        
        total = len(codes)
        if total == 0:
            logger.info("没有需要补全的股票 ✅")
            storage.disconnect()
            return
        
        start_idx = int(args.start)
        if start_idx > 0:
            codes = codes[start_idx:]
        
        if args.limit > 0:
            codes = codes[:args.limit]
        
        logger.info(f"需补全股票: {len(codes)} 只（从 #{start_idx} 开始）")
        
        success = 0
        fail = 0
        total_records = 0
        
        for i, code in enumerate(codes):
            # 检查是否已有足够数据
            if args.check_2026:
                cursor = storage.conn.cursor()
                cursor.execute("""
                    SELECT COUNT(DISTINCT trade_date) 
                    FROM stock_quotes 
                    WHERE code = %s AND cycle = '1d'
                        AND trade_date >= '2026-01-01' AND trade_date <= '2026-05-31'
                """, (code,))
                existing = cursor.fetchone()[0]
                cursor.close()
            else:
                cursor = storage.conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM stock_quotes WHERE code = %s", (code,))
                existing = cursor.fetchone()[0]
                cursor.close()
            
            if existing >= args.min_days and not args.force:
                logger.debug(f"  [{start_idx+i+1}/{total}] {code}: 已有 {existing} 天数据，跳过")
                continue
            
            logger.info(f"  [{start_idx+i+1}/{total}] 补全 {code}（已有 {existing} 天）...")
            if args.check_2026:
                count = import_stock_via_baostock(storage, code, 
                                                 start_date='2026-01-01', 
                                                 end_date='2026-05-31')
            else:
                count = import_stock_via_baostock(storage, code)
            
            if count > 0:
                success += 1
                total_records += count
                logger.info(f"    ✅ 导入 {count} 条")
            else:
                fail += 1
            
            # 每 50 只进度报告
            if (i + 1) % 50 == 0:
                logger.info(f"  进度: {i+1}/{len(codes)}, 成功 {success}, 失败 {fail}, 记录 {total_records}")
            
            # 避免请求过快
            if i % 10 == 9:
                time.sleep(0.5)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 补全完成")
        logger.info(f"  处理: {len(codes)} 只")
        logger.info(f"  成功: {success} 只")
        logger.info(f"  失败: {fail} 只")
        logger.info(f"  记录: {total_records} 条")
        logger.info(f"{'='*60}")
    
    storage.disconnect()


if __name__ == '__main__':
    main()